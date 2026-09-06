# M-33.6g JDK identity boundary

`M336PrivateJdkObservation` holds local executable, release-file, and provider-root `Path` objects plus the observed banner. It is private and must stay outside Git/public roots.

`M336PublicJdkIdentityReceipt` contains the frozen provider manifest, provider/platform role, target release, invocation-policy hash, platform-neutral compiler semantic identity, expected vendor/version/build, exact binary/release hashes, normalized banner hash, status, and receipt hash. Its schema has no path/home/root/location field. No published hash is derived only from a path.

The platform-neutral compiler identity matches the production compilation probe; platform binary hashes remain separate public-safe telemetry.
