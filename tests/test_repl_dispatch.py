"""
test_repl_dispatch.py
Automated test suite verifying Living Language Console hotkey dispatch,
bridge functions, and exception resilience in osiris_repl.py and osiris_termux_console.py.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

import osiris_termux_console as otc
from osiris_cli.osiris_repl import dispatch_command, OsirisReplState


class TestReplDispatchBridge(unittest.TestCase):
    def setUp(self):
        self.state = OsirisReplState()

    def test_otc_bridge_methods_exist(self):
        """Verify all 7 previously missing bridge methods exist and are callable on otc."""
        bridge_methods = [
            '_intent',
            '_runs',
            '_apply',
            '_discard',
            '_organism',
            '_sprint',
            '_nclm',
        ]
        for name in bridge_methods:
            self.assertTrue(hasattr(otc, name), f"Missing method {name} on osiris_termux_console")
            self.assertTrue(callable(getattr(otc, name)), f"Attribute {name} is not callable")

    def test_intent_bridge(self):
        """Test _intent bridge handles status and confidence queries without crashing."""
        with patch.object(otc, '_intent_status') as mock_status:
            otc._intent()
            mock_status.assert_called_once()

        with patch.object(otc, '_intent_status') as mock_status:
            otc._intent("/intent status")
            mock_status.assert_called_once()

    def test_runs_bridge(self):
        """Test _runs bridge differentiates show vs stats."""
        with patch.object(otc, '_runs_stats') as mock_stats, \
             patch.object(otc, '_run_show') as mock_show:
            otc._runs("/runs")
            mock_stats.assert_called_once()
            mock_show.assert_not_called()

        with patch.object(otc, '_runs_stats') as mock_stats, \
             patch.object(otc, '_run_show') as mock_show:
            otc._runs("/run show")
            mock_show.assert_called_once_with("/run show")
            mock_stats.assert_not_called()

    def test_apply_and_discard_bridge(self):
        """Test _apply and _discard call their respective write management functions."""
        with patch.object(otc, '_apply_pending_write') as mock_apply:
            otc._apply()
            mock_apply.assert_called_once()

        with patch.object(otc, '_discard_pending_write') as mock_discard:
            otc._discard()
            mock_discard.assert_called_once()

    def test_organism_bridge(self):
        """Test _organism routes alerts vs status."""
        with patch.object(otc, '_organism_status') as mock_status, \
             patch.object(otc, '_organism_alerts') as mock_alerts:
            otc._organism("/organism")
            mock_status.assert_called_once()
            mock_alerts.assert_not_called()

        with patch.object(otc, '_organism_status') as mock_status, \
             patch.object(otc, '_organism_alerts') as mock_alerts:
            otc._organism("/organism alerts 5")
            mock_alerts.assert_called_once_with(n=5)
            mock_status.assert_not_called()

    def test_sprint_bridge(self):
        """Test _sprint routes plan, execute, and review."""
        with patch.object(otc, '_sprint_plan') as mock_plan:
            otc._sprint("/sprint plan")
            mock_plan.assert_called_once_with("/sprint plan")

        with patch.object(otc, '_sprint_execute') as mock_exec:
            otc._sprint("/sprint execute #1")
            mock_exec.assert_called_once_with("/sprint execute #1")

        with patch.object(otc, '_sprint_review') as mock_review:
            otc._sprint("/sprint review")
            mock_review.assert_called_once()

    def test_nclm_bridge(self):
        """Test _nclm routes to _organism_status."""
        with patch.object(otc, '_organism_status') as mock_status:
            otc._nclm("/nclm")
            mock_status.assert_called_once()

    def test_mentors_signature_tolerance(self):
        """Test _mentors accepts optional argument without TypeError."""
        with patch('protege.load_ledger', return_value=([], None)), \
             patch('protege.candidates', return_value=([], [])):
            # Both 0-arg and 1-arg calls must succeed
            try:
                otc._mentors()
                otc._mentors("/mentors")
            except TypeError as te:
                self.fail(f"_mentors raised TypeError: {te}")

    def test_facts_signature_tolerance(self):
        """Test _facts accepts optional argument without TypeError."""
        try:
            otc._facts()
            otc._facts("/facts")
        except TypeError as te:
            self.fail(f"_facts raised TypeError: {te}")

    def test_consensus_signature_tolerance(self):
        """Test _consensus accepts string, integer, or default without TypeError."""
        try:
            otc._consensus()
            otc._consensus(10)
            otc._consensus("/consensus 5")
            otc._consensus("/consensus")
        except TypeError as te:
            self.fail(f"_consensus raised TypeError: {te}")

    def test_hotkey_b_intent_status_dispatch(self):
        """Direct regression test for hotkey B crash."""
        otc._pending_suggestions['B'] = '/intent status'
        with patch.object(otc, '_intent_status') as mock_intent:
            dispatch_command(self.state, 'B')
            mock_intent.assert_called_once()

    def test_all_home_letter_hotkeys_dispatch(self):
        """Verify all letter hotkeys registered in _home_letters() dispatch without exceptions."""
        letters = otc._home_letters()
        for key, label, cmd in letters:
            otc._pending_suggestions[key] = cmd
            with patch.object(otc, '_gap', return_value=None), \
                 patch.object(otc, '_experiment', return_value=None), \
                 patch.object(otc, '_bench', return_value=None), \
                 patch.object(otc, '_ask', return_value="0"):
                try:
                    dispatch_command(self.state, key)
                except Exception as e:
                    self.fail(f"Hotkey [{key}] -> '{cmd}' raised exception: {type(e).__name__}: {e}")

    def test_repl_fault_isolation(self):
        """Verify that an unexpected exception in otc does not crash dispatch_command."""
        with patch.object(otc, '_intent', side_effect=RuntimeError("simulated unexpected failure")):
            # Must not raise RuntimeError
            try:
                dispatch_command(self.state, "/intent status")
            except Exception as e:
                self.fail(f"dispatch_command failed to isolate exception: {e}")


if __name__ == '__main__':
    unittest.main()
