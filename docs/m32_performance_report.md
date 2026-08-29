# M-32 performance report

Exact-H11 CPU-only samples use three iterations and Python peak memory measured with `tracemalloc`.

| Operation | Windows p50/p95/p99 ms | Karina p50/p95/p99 ms | Windows/Karina peak bytes |
|---|---:|---:|---:|
| source load | 4.783/12.449/12.449 | 1.651/1.752/1.752 | 58,385/53,880 |
| segmentation | 72.247/73.277/73.277 | 32.123/32.652/32.652 | 236,437/232,173 |
| proposal generation | 30.628/30.772/30.772 | 19.179/19.208/19.208 | 101,746/101,621 |
| pack compilation | 254.437/257.245/257.245 | 124.307/128.125/128.125 | 1,237,905/1,237,545 |
| provider closure | 385.087/394.020/394.020 | 127.086/127.532/127.532 | 75,159/70,738 |
| installed currentness | 4,945.423/4,960.382/4,960.382 | 1,916.857/1,923.255/1,923.255 | 3,000,088/3,001,881 |
| held-out runtime solution | 0.264/0.354/0.354 | 0.158/0.215/0.215 | 3,648/3,648 |

Compilation and runtime query time are reported separately. Both measurements report `runtime_network=false`, `trusted_cpu_only=true`, and status `PASS`; complete throughput and operation rows are in the evidence JSON files.
