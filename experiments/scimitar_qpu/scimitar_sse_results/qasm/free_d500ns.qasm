OPENQASM 3.0;
include "stdgates.inc";
bit[1] meas;
qubit[1] q;
h q[0];
delay[500ns] q[0];
h q[0];
meas[0] = measure q[0];
