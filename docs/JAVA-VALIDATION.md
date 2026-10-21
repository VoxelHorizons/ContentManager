# P0 Java pack validation bridge (opt-in, source staging only)

**Status:** implemented external Java subprocess bridge, **not** end-to-end
Paper runtime certification. Unlike Content Manager's Python \`lint\`, this
executes the real \`JavaPackCompiler.validate(...)\` supplied by VoxelCore.
It never writes to the selected pack and never publishes a ZIP.

## Source contract

Verified VoxelCore \`main\` commit \`1b6489c5d396c119f9f6e0326eabb1b2aeaf5b39\`:

- \`voxelcore-pack/.../JavaPackCompiler.java\`:
  \`validate(Path contentRoot, Path allocationManifestPath, JavaPackTarget)\`
  executes the full pack pipeline with \`writeOutput=false\`.
- \`JavaPackTarget.java\`: exact \`mc-26.3\` target uses format **97.1**,
  \`mc-26.2\` uses **88.0**.
- \`JavaPackBuildResult.java\`: renderedItems/renderedBlocks/copiedAssets counts.
- \`ContentPackDiscovery.java\`: content root contains one directory per pack.

This revision is a **documented reference**, not cryptographic verification of
whatever libraries an operator supplies in a classpath file. Until dependency
provenance is enforced, report \`compiler_classpath_attested: false\`.

## Build a classpath from a checked-out VoxelCore source tree

Requires a **JDK with source-file launch support (recommend Java 25)**, Maven
and a checked-out VoxelCore source revision. The checked-out revision should be
the exact commit above for initial reproducibility. Follow the Maven setup and
repository dependencies in VoxelCore's root \`pom.xml\`.

PowerShell example (adapt source and output directories):

\`\`\`powershell
$vc = "C:\Development\VoxelCore"
$cm = "C:\Development\ContentManager"
git -C $vc rev-parse HEAD  # compare with the pinned SHA documented above
mvn -B -f "$vc\pom.xml" -pl voxelcore-pack -am -DskipTests install
mvn -B -f "$vc\voxelcore-pack\pom.xml" dependency:build-classpath "-Dmdep.includeScope=test" "-Dmdep.outputFile=$cm\voxelcore-deps.txt"
$deps = (Get-Content "$cm\voxelcore-deps.txt" -Raw).Trim()
"$vc\voxelcore-pack\target\classes;$vc\voxelcore-common\target\classes;$deps" |
  Set-Content "$cm\voxelcore-classpath.txt" -NoNewline
\`\`\`

On Linux/macOS use Maven's same two commands; generate a classpath file whose
entries are joined by \`:\` rather than \`;\`. You **must** include VoxelCore
pack/common classes and runtime dependencies (Gson, Bukkit API, SnakeYAML,
etc.). This workflow does not download source or binaries silently.

## Validate a pack / golden fixture

\`\`\`bash
python -m content_manager validate-java /path/to/plugins/VoxelCore/content \
  --classpath-file /path/to/voxelcore-classpath.txt \
  --target mc-26.3 --json
\`\`\`

In PowerShell, use one line or its native backtick line continuation.

For realistic allocations add
\`--allocations /path/to/render-allocations.yml\`. The original allocations
are read-only and copied into the temporary workspace. Never point at runtime
world state or live build outputs.

Synthetic cases live in \`tests/fixtures/java_valid\` and
\`tests/fixtures/java_invalid_duplicate\`. They are deliberately tiny and
contain no copyrighted Minecraft images. Given a classpath, run the valid
fixture and confirm exit **0**, then the invalid render fixture and confirm a **nonzero** exit
from the Java validator. The duplicate-key fixture checks Python's early
YAML rejection separately. Python unit tests verify staging, no source mutation,
fail-closed results, classpath, timeout and path safety; these are **not** a
substitute for executing the actual JVM/compiler.

## Safety and output contract

- The bridge copies only the chosen authored pack trees, excluding
  \`.contentmanager\`, \`.git\` and Python caches, into a temporary directory.
  Symlinks, reparse points, non-regular input files, source drift and oversized
  input sets fail before validation.
- The compiler is launched with argument arrays (no shell), a bounded timeout
  and external classpath supplied explicitly; it cannot publish a ZIP through
  this bridge. Its logs are truncated to a bounded output size.
- Returns JSON \`schema_version: 1\`, compiler target, input digest and file
  count, validation counts, process log and explicit \`runtime_paper_tested:
  false\`. A zero exit without the exact success marker is **not** accepted.
- Error exit **1** does not imply specific Minecraft render/shader correctness;
  success proves only that the supplied VoxelCore Java pack validator returned
  success on the staged inputs.
- **Not yet implemented:** source-classpath SHA attestation, automated
  distributable checksum attestation, real addon parser fixtures, final ZIP
  rendering, Paper staging,
  allocation integrity certification and production-safe deployment.

The next P0 step is an automated pinned VoxelCore Java CI job with an actual
classpath/Java 25 build, then representative real-world fixture coverage.

## Pinned CI acceptance job

`.github/workflows/java-contract.yml` runs the Maven build from the exact
VoxelCore source revision above using JDK 25 and then invokes the bridge on
both fixture packs. It is intentionally separate from the lightweight Python
matrix. This verifies more than a mocked Java process; it is still **pack
compiler-only**, not an installed Paper server or Furniture/Vehicles test.
