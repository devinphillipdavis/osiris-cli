#!/usr/bin/env python3
"""3-Way DDPM Finite-State Operator Comparison:
1. Row-normalized sampled Gaussian kernel (P_sampled)
2. Cell-integrated Gaussian kernel with infinite endpoint bins (P_cell)
3. Reversible finite-state Ornstein-Uhlenbeck CTMC (exp(b_n * Q_0))

Persists dual-substrate execution invariants and tracks TV, W2, KL, and
Shannon entropy H(p) across all three trajectories.

Required: numpy
Optional: scipy, matplotlib, osiris_hardware_mesh
"""

import math
import os
from pathlib import Path
import platform
import sys
import numpy as np

try:
    from scipy.special import erfc as _erfc  # type: ignore
    ERFC_BACKEND = "scipy.special.erfc"
except ImportError:
    _erfc_vec = np.frompyfunc(math.erfc, 1, 1)

    def _erfc(x):
        return _erfc_vec(np.asarray(x, dtype=float)).astype(float)

    ERFC_BACKEND = "math.erfc (stdlib vectorized)"


def configure_substrate():
    """Probe hardware substrate dynamically without hardcoded paths."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    arch = platform.machine().lower()
    uname = os.uname().release.lower() if hasattr(os, "uname") else ""

    try:
        import osiris_hardware_mesh as mesh  # type: ignore
        substrate = getattr(mesh, "ACTIVE_NODE", None) or arch
        timeout_s = float(getattr(mesh, "TIMEOUT_S", 300.0))
    except ImportError:
        is_mobile_edge = ("aarch64" in arch or "arm64" in arch) and (
            "android" in uname or "termux" in os.environ.get("PREFIX", "").lower()
        )
        substrate = "Node_Alpha_ARM64_Edge" if is_mobile_edge else f"Node_Beta_{arch}"
        timeout_s = 300.0 if is_mobile_edge else 1800.0

    return {
        "substrate": substrate,
        "arch": arch,
        "timeout_s": timeout_s,
        "erfc_backend": ERFC_BACKEND,
    }


def normal_cdf_diff(z_low, z_high):
    """Tail-safe evaluation of Phi(z_high) - Phi(z_low) using erfc.

    Supports z_low = -inf and z_high = +inf without NaN or catastrophic
    cancellation in extreme positive or negative tails.
    """
    u_low = np.asarray(z_low, dtype=float) / np.sqrt(2.0)
    u_high = np.asarray(z_high, dtype=float) / np.sqrt(2.0)

    out = np.empty(np.broadcast_shapes(u_low.shape, u_high.shape), dtype=float)

    neg_mask = u_high <= 0.0
    pos_mask = u_low >= 0.0
    mid_mask = ~(neg_mask | pos_mask)

    if np.any(neg_mask):
        out[neg_mask] = 0.5 * (
            _erfc(-u_high[neg_mask]) - _erfc(-u_low[neg_mask])
        )
    if np.any(pos_mask):
        out[pos_mask] = 0.5 * (
            _erfc(u_low[pos_mask]) - _erfc(u_high[pos_mask])
        )
    if np.any(mid_mask):
        out[mid_mask] = 1.0 - 0.5 * (
            _erfc(-u_low[mid_mask]) + _erfc(u_high[mid_mask])
        )

    return np.maximum(out, 0.0)


def sampled_transition(s, beta):
    """Section 2.1: Row-normalized point-sampled Gaussian kernel."""
    if not 0.0 < beta < 1.0:
        raise ValueError("Each beta must lie strictly between 0 and 1.")

    a = np.sqrt(1.0 - beta)
    logw = -(s[None, :] - a * s[:, None]) ** 2 / (2.0 * beta)

    row_max = logw.max(axis=1, keepdims=True)
    w_scaled = np.exp(logw - row_max)
    row_sum = w_scaled.sum(axis=1)
    P = w_scaled / row_sum[:, None]

    # Exact reversible invariant distribution for fixed beta
    log_r = row_max[:, 0] + np.log(row_sum)
    log_pi = -0.5 * s**2 + log_r
    pi_P = np.exp(log_pi - log_pi.max())
    pi_P /= pi_P.sum()
    return P, pi_P


def cell_integrated_transition(s, beta):
    """Section 2.3: Cell-integrated Gaussian kernel with infinite outer bins."""
    if not 0.0 < beta < 1.0:
        raise ValueError("Each beta must lie strictly between 0 and 1.")

    h = s[1] - s[0]
    if not np.allclose(np.diff(s), h):
        raise ValueError("A uniform grid is required.")

    edges = np.empty(len(s) + 1, dtype=float)
    edges[0] = -np.inf
    edges[1:-1] = s[:-1] + 0.5 * h
    edges[-1] = np.inf

    mean = np.sqrt(1.0 - beta) * s[:, None]
    sigma = np.sqrt(beta)

    z_low = (edges[:-1][None, :] - mean) / sigma
    z_high = (edges[1:][None, :] - mean) / sigma

    P_cell = normal_cdf_diff(z_low, z_high)
    # Row sums are already 1.0 to machine precision; normalize roundoff only
    P_cell /= P_cell.sum(axis=1, keepdims=True)
    return P_cell, edges


def stationary_distribution(P):
    """Compute unique left stationary distribution pi @ P = pi via linear solve."""
    n = P.shape[0]
    A = P.T - np.eye(n)
    A[-1, :] = 1.0
    b = np.zeros(n, dtype=float)
    b[-1] = 1.0
    pi = np.linalg.solve(A, b)
    return clean_probability(pi)


def generator(s):
    """Section 4: Reversible nearest-neighbor CTMC generator Q_0."""
    h = s[1] - s[0]
    if not np.allclose(np.diff(s), h):
        raise ValueError("A uniform grid is required.")

    n = len(s)
    U = 0.5 * s**2
    dU = np.diff(U)
    Q = np.zeros((n, n))

    i = np.arange(n - 1)
    Q[i, i + 1] = np.exp(-0.5 * dU) / (2.0 * h**2)
    Q[i + 1, i] = np.exp(0.5 * dU) / (2.0 * h**2)
    Q[np.diag_indices(n)] = -Q.sum(axis=1)

    pi_Q = np.exp(-U)
    pi_Q /= pi_Q.sum()
    return Q, pi_Q


def discrete_w2(p, q, s):
    """Exact 1D W2 for discrete probability measures on the same sorted grid."""
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)

    ip = np.flatnonzero(p > 0.0)
    iq = np.flatnonzero(q > 0.0)
    if not len(ip) or not len(iq):
        raise ValueError("Probability measures must have positive mass.")

    pp = p[ip] / p[ip].sum()
    qq = q[iq] / q[iq].sum()

    i = j = 0
    a, b = pp[0], qq[0]
    cost = 0.0

    while i < len(ip) and j < len(iq):
        mass = min(a, b)
        cost += mass * (s[ip[i]] - s[iq[j]]) ** 2

        if a < b:
            b -= a
            i += 1
            if i < len(ip):
                a = pp[i]
        elif b < a:
            a -= b
            j += 1
            if j < len(iq):
                b = qq[j]
        else:
            i += 1
            j += 1
            if i < len(ip):
                a = pp[i]
            if j < len(iq):
                b = qq[j]

    return float(np.sqrt(max(cost, 0.0)))


def kl(p, pi):
    mask = p > 0.0
    return float(np.sum(p[mask] * np.log(p[mask] / pi[mask])))


def shannon_entropy(p):
    """Discrete Shannon entropy H(p) = -sum p_i log(p_i) for NCLM telemetry."""
    mask = p > 0.0
    return float(-np.sum(p[mask] * np.log(p[mask])))


def total_variation(p, q):
    return float(0.5 * np.abs(p - q).sum())


def clean_probability(p):
    """Repair roundoff only; reject materially negative output."""
    if p.min() < -1e-10:
        raise ArithmeticError("Materially negative probability encountered.")
    p = np.maximum(p, 0.0)
    return p / p.sum()


def terminal_heatmap(history, s, title="Sampled", rows=10, columns=61):
    levels = " .:-=+*#%@"
    indices = np.linspace(0, len(s) - 1, columns).astype(int)
    steps = np.unique(np.linspace(0, len(history) - 1, rows).astype(int))

    scale = history.max()
    print(f"\n[{title}] Probability mass evolution: s in [{s[0]}, {s[-1]}]")
    for k in steps:
        v = history[k, indices] / max(scale, 1e-300)
        text = "".join(
            levels[min(int(x * (len(levels) - 1)), len(levels) - 1)]
            for x in v
        )
        print(f"{k:4d} |{text}|")


def main():
    ctx = configure_substrate()
    out = Path.cwd() / "output"
    out.mkdir(exist_ok=True)

    L, N, T = 6.0, 121, 240
    s = np.linspace(-L, L, N)
    h = s[1] - s[0]

    beta = np.linspace(0.01, 0.08, T)
    B = np.r_[0.0, np.cumsum(-np.log1p(-beta))]

    Q, pi_Q = generator(s)
    assert np.allclose(Q.sum(axis=1), 0.0, atol=1e-11)
    assert np.allclose(pi_Q @ Q, 0.0, atol=1e-11)
    assert np.allclose(pi_Q[:, None] * Q, pi_Q[None, :] * Q.T, atol=1e-11)

    # Exact cell-integrated standard normal measure on the bins C_j
    _, edges = cell_integrated_transition(s, beta[0])
    pi_Phi = normal_cdf_diff(edges[:-1], edges[1:])
    pi_Phi /= pi_Phi.sum()

    root = np.sqrt(pi_Q)
    S = root[:, None] * Q / root[None, :]
    assert np.allclose(S, S.T, atol=1e-11)

    eig, V = np.linalg.eigh(0.5 * (S + S.T))
    assert eig[-1] < 1e-9
    eig[-1] = 0.0
    gap = -eig[-2]

    p0 = (
        0.65 * np.exp(-0.5 * ((s + 2.3) / 0.35) ** 2)
        + 0.35 * np.exp(-0.5 * ((s - 2.0) / 0.55) ** 2)
    )
    p0 /= p0.sum()

    sampled = np.empty((T + 1, N))
    cell_int = np.empty_like(sampled)
    ctmc = np.empty_like(sampled)
    sampled[0] = cell_int[0] = ctmc[0] = p0

    coefficients = (p0 / root) @ V

    for n, beta_n in enumerate(beta, start=1):
        P_samp, pi_P_samp = sampled_transition(s, beta_n)
        P_cell, _ = cell_integrated_transition(s, beta_n)

        assert np.allclose(P_samp.sum(axis=1), 1.0)
        assert np.allclose(P_cell.sum(axis=1), 1.0)
        assert np.allclose(pi_P_samp @ P_samp, pi_P_samp, atol=1e-12)

        sampled[n] = sampled[n - 1] @ P_samp
        cell_int[n] = cell_int[n - 1] @ P_cell
        raw = ((coefficients * np.exp(B[n] * eig)) @ V.T) * root
        ctmc[n] = clean_probability(raw)

    pi_P_cell_final = stationary_distribution(P_cell)

    metrics = np.array([
        [
            n,
            B[n],
            total_variation(sampled[n], pi_Q),
            total_variation(cell_int[n], pi_Q),
            total_variation(ctmc[n], pi_Q),
            total_variation(cell_int[n], pi_Phi),
            discrete_w2(sampled[n], pi_Q, s),
            discrete_w2(cell_int[n], pi_Q, s),
            discrete_w2(ctmc[n], pi_Q, s),
            kl(sampled[n], pi_Q),
            kl(cell_int[n], pi_Q),
            kl(ctmc[n], pi_Q),
            shannon_entropy(sampled[n]),
            shannon_entropy(cell_int[n]),
            shannon_entropy(ctmc[n]),
        ]
        for n in range(T + 1)
    ])

    np.savez_compressed(
        out / "ddpm_markov_histories.npz",
        s=s,
        edges=edges,
        beta=beta,
        B=B,
        Q=Q,
        pi_Q=pi_Q,
        pi_Phi=pi_Phi,
        sampled=sampled,
        cell_int=cell_int,
        ctmc=ctmc,
    )
    np.savetxt(
        out / "ddpm_markov_metrics.csv",
        metrics,
        delimiter=",",
        header=(
            "step,B,TV_sampled_piQ,TV_cell_piQ,TV_ctmc_piQ,TV_cell_piPhi,"
            "W2_sampled,W2_cell,W2_ctmc,KL_sampled,KL_cell,KL_ctmc,"
            "H_sampled,H_cell,H_ctmc"
        ),
        comments="",
    )

    print(f"Substrate context: {ctx['substrate']} (timeout={ctx['timeout_s']}s)")
    print(f"erfc backend:      {ctx['erfc_backend']}")
    print(f"Operational horizon B_T:      {B[-1]:.6f}")
    print(f"Signal retention alpha_bar_T: {np.exp(-B[-1]):.6e}")
    print(f"Finite-grid CTMC spectral gap: {gap:.6f}")
    print("-" * 62)
    print(f"Final TV to pi_Q   | Sampled: {metrics[-1, 2]:.6e}")
    print(f"Final TV to pi_Q   | Cell:    {metrics[-1, 3]:.6e}")
    print(f"Final TV to pi_Q   | CTMC:    {metrics[-1, 4]:.6e}")
    print(f"Final TV to pi_Phi | Cell:    {metrics[-1, 5]:.6e}")
    print("-" * 62)
    print(f"Final W2 to pi_Q   | Sampled: {metrics[-1, 6]:.6e}")
    print(f"Final W2 to pi_Q   | Cell:    {metrics[-1, 7]:.6e}")
    print(f"Final W2 to pi_Q   | CTMC:    {metrics[-1, 8]:.6e}")
    print(
        f"Final Shannon H(p) | Sampled: {metrics[-1, 12]:.6f} | "
        f"Cell: {metrics[-1, 13]:.6f} | CTMC: {metrics[-1, 14]:.6f}"
    )
    print(
        "Stationary bias at beta_T vs pi_Q (TV) | "
        f"Sampled: {total_variation(pi_P_samp, pi_Q):.6e} | "
        f"Cell: {total_variation(pi_P_cell_final, pi_Q):.6e}"
    )

    terminal_heatmap(cell_int, s, title="Cell-Integrated")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Matplotlib unavailable; terminal visualization completed.")
        return

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.8), constrained_layout=True)

    image = axes[0].imshow(
        cell_int.T / h,
        origin="lower",
        aspect="auto",
        extent=[0, T, s[0], s[-1]],
        cmap="magma",
    )
    axes[0].set(
        title="Cell-integrated marginal evolution",
        xlabel="DDPM step n",
        ylabel="State",
    )
    fig.colorbar(image, ax=axes[0], label="Approximate density")

    axes[1].plot(s, sampled[-1] / h, label="Sampled final", lw=1.6)
    axes[1].plot(s, cell_int[-1] / h, "--", label="Cell-integrated final", lw=1.6)
    axes[1].plot(s, ctmc[-1] / h, "-.", label="CTMC final", lw=1.6)
    axes[1].plot(s, pi_Q / h, "k:", lw=2.0, label="Equilibrium pi_Q")
    axes[1].set(
        title=f"Final marginals at T={T} vs equilibrium",
        xlabel="State",
        ylabel="Approximate density",
    )
    axes[1].legend(fontsize=8)

    tiny = 1e-16
    axes[2].semilogy(
        B, np.maximum(metrics[:, 2], tiny), label="Sampled TV to pi_Q"
    )
    axes[2].semilogy(
        B, np.maximum(metrics[:, 3], tiny), label="Cell TV to pi_Q"
    )
    axes[2].semilogy(
        B, np.maximum(metrics[:, 5], tiny), ":", label="Cell TV to pi_Phi"
    )
    axes[2].semilogy(
        B, np.maximum(metrics[:, 4], tiny), label="CTMC TV to pi_Q"
    )

    chi2_initial = np.sum((p0 - pi_Q) ** 2 / pi_Q)
    tv_bound = np.minimum(1.0, 0.5 * np.sqrt(chi2_initial) * np.exp(-gap * B))
    axes[2].semilogy(
        B, np.maximum(tv_bound, tiny), "k--", label="CTMC spectral bound"
    )
    axes[2].set(
        title="3-Way convergence diagnostics",
        xlabel="Operational time B",
        ylabel="Total variation",
    )
    axes[2].legend(fontsize=8)

    fig.savefig(out / "ddpm_markov_diagnostics.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
