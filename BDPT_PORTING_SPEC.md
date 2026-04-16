This is analysis, not a code-change task.

**Assumptions**
- Source of truth is the CPU rendering core in:
  - `/home/runner/work/LuxCore/LuxCore/src/slg/engines/bidircpu/*`
  - `/home/runner/work/LuxCore/LuxCore/src/slg/engines/bidirvmcpu/*`
- `BIDIRCPU` is the explicit BDPT implementation.
- `BIDIRVMCPU` is BDPT + vertex merging (VCM-style hybrid).
- Legacy Lux parser maps `SurfaceIntegrator "bidirectional"` to `BIDIRVMCPU`, not `BIDIRCPU` (`/src/luxcore/luxparser/luxparse.cpp`).
- Goal is physics-correct Mitsuba 3 porting, not UI/AOV parity.

---

## Core Light Transport Model

**Objective**
- Estimate image formation as a **path-space integral** over sensor-connected light transport paths.
- Unbiased only for the pure BDPT core **when**:
  - variance clamping is off,
  - PhotonGI cache is off,
  - Lux-specific heuristic shortcuts are ignored or reproduced carefully.

**Equation being solved**
- Standard rendering equation in path form:
  \[
  I = \int_{\mathcal P} f(\bar x)\, d\mu(\bar x)
  \]
  where a path \(\bar x = (x_0,\dots,x_k)\) starts on the sensor and ends on an emitter/environment, with contribution assembled from:
  - sensor response,
  - emitted radiance,
  - BSDF/phase evaluations,
  - geometry terms,
  - visibility,
  - medium transmittance / scattering.

**How paths are constructed**
- **Both** eye and light subpaths are constructed explicitly.
- Eye side:
  - camera ray generation,
  - surface/medium intersections,
  - NEE,
  - direct emitter hit,
  - connection to light subpath vertices.
- Light side:
  - emitter selection,
  - emitter ray emission,
  - surface/medium intersections,
  - connection to camera,
  - optionally vertex merging in `BIDIRVMCPU`.

**Path space parameterization**
- Vertices:
  - sensor endpoint,
  - emitter endpoint,
  - internal surface vertices,
  - internal medium scattering vertices.
- Measures:
  - local extension PDFs tracked in **solid angle**,
  - converted to **area** when evaluating alternative connection techniques via `PdfWtoA(pdfW, dist, cos)`.
- Endpoint convention:
  - Lux depth counts **non-endpoint transport vertices**; sensor/emitter endpoints are implicit.

---

## Integrator Architecture

**Explicit vs implicit BDPT**
- **Explicit BDPT exists**: `BIDIRCPU`.
- **Hybrid integrator also exists**: `BIDIRVMCPU` adds vertex merging/hash grid, i.e. VCM-like behavior.

**Sampling strategy**
- Light subpath:
  - choose light with `emitLightStrategy`,
  - sample emitted ray,
  - trace and store only **non-delta** internal vertices.
- Eye subpath:
  - sample camera ray,
  - trace through scene,
  - at each non-delta vertex:
    - sample direct lighting,
    - connect to all light-path vertices,
    - in `BIDIRVMCPU`, also merge against nearby light vertices.

**Connection strategy**
- Techniques present:
  1. camera path directly hits emitter/environment,
  2. eye-path NEE to a sampled light,
  3. light-path connection directly to camera,
  4. eye/light vertex connection,
  5. vertex merging (`BIDIRVMCPU` only).

**MIS formulation**
- Heuristic:
  - `MIS(a) = a^2` (power heuristic with exponent 2).
- Core state:
  - `dVCM`, `dVC`, `dVM` follow Georgiev/SmallVCM-style recurrence ratios.
- In pure BDPT:
  - `misVmWeightFactor = 0`,
  - `misVcWeightFactor = 0`,
  - so merging terms are disabled.
- In `BIDIRVMCPU`:
  - both are nonzero and depend on merge radius / light-path count.

**Russian roulette / termination**
- Max depths:
  - `path.maxdepth` for eye,
  - `light.maxdepth` for light.
- RR starts at `path.russianroulette.depth`.
- Survival probability:
  \[
  p_{rr} = \mathrm{clamp}(\mathrm{Filter}(\beta), \text{cap}, 1)
  \]
- If survived, throughput is divided by \(p_{rr}\).

---

## Data Flow & State

**Path vertex state**
- `PathVertexVM` contains:
  - `BSDF bsdf`
  - `BSDFEvent bsdfEvent`
  - `Spectrum throughput`
  - `u_int lightID`
  - `u_int depth`
  - `float dVCM, dVC, dVM`
  - `PathVolumeInfo volInfo`

**What `BSDF`/hit point contributes**
- Position `p`
- Geometry normal `geometryN`
- Shading normal `shadeN`
- Incoming/fixed direction `fixedDir`
- `fromLight`
- `intoObject`
- interior/exterior volumes
- pass-through event seed
- shadow-transparency flag

**How PDFs are tracked**
- Extension:
  - BSDF sampling gives forward pdf in solid angle.
  - Reverse pdf is either equal for specular or recomputed with `Pdf()`.
- Connections:
  - convert solid-angle pdfs to area pdfs before MIS.
- Endpoints:
  - light emission stores emission pdf in solid angle,
  - camera uses `GetPDF()` and sometimes `fluxToRadianceFactor`.

**Important invariant**
- `throughput` is **already weighted** by Lux wrappers:
  - `BSDF::Sample()` already includes \(f \cos / p\),
  - light emission initialization divides by light emission pdf,
  - `BSDF::Evaluate()` already includes a cosine convention on the “light side” for surfaces.
- Therefore:
  - **do not reapply cos/pdf blindly** in Mitsuba.

**Correctness invariants**
- `fixedDir` orientation must match `fromLight`.
- `volInfo` must be updated after every transmitted/scattering event.
- `dVC*` recurrence must be updated with the same measure conversions as Lux.
- Delta vertices are never used for generic connection/merging.
- Reverse PDFs must correspond to the same measure as forward PDFs before MIS comparison.

---

## Material / BSDF Interaction Model

**Scattering evaluation**
- `BSDF::Evaluate(dir)`:
  - rejects invalid hemisphere/side combinations,
  - transforms to local frame,
  - calls material `Evaluate(localLightDir, localEyeDir, ...)`,
  - applies:
    - shadow terminator correction for non-specular reflection,
    - adjoint correction when tracing from light.

**Sampling**
- `BSDF::Sample()`:
  - samples outgoing direction from material,
  - returns a value already containing Lux’s sampling weight,
  - applies adjoint correction on light-traced paths.

**PDF separation**
- Lux material interface is explicitly split into:
  - `Evaluate()`
  - `Sample()`
  - `Pdf()`
- `Pdf()` returns both direct and reverse PDFs, needed by BDPT MIS.

**Deviations from standard Mitsuba-style BSDFs**
- Surface `Evaluate()` is not raw \(f\); it uses Lux’s cosine convention.
- `Sample()` is not raw \(f\); it is already \(f \cos / p\)-weighted.
- Adjoint factor is applied in BSDF wrapper, not only in MIS logic.
- Shadow terminator compensation is non-physical.

---

## Light Sampling

**Light selection**
- Uses `GetEmitLightStrategy()` even for direct-light sampling in BDPT.
- Default strategy is log-power weighted.
- This is notable because Lux also has `illuminateLightStrategy`, but BDPT does not use it here.

**Area vs delta lights**
- Intersectable area emitters:
  - can be hit directly by camera/paths,
  - support `GetRadiance()`,
  - support `Emit()` and `Illuminate()`.
- Non-intersectable delta/infinite lights:
  - cannot be hit as geometry,
  - contribute via `Emit()` / `Illuminate()` / environment query.
- Light vertex 0 (the emitter endpoint) is **not stored** in the light path.
- Only non-delta scattered light vertices are stored and connected.

**Connection logic**
- Eye → sampled light: NEE (`DirectLightSampling`)
- Eye ↔ light vertex: explicit connection (`ConnectVertices`)
- Light vertex → camera: explicit sensor connection (`ConnectToEye`)
- Eye directly hits emitter/environment: `DirectHitLight`
- `BIDIRVMCPU` adds eye/light vertex merging via hash grid.

---

## Numerical / Physical Assumptions

**Units / scaling**
- Light path initialization:
  \[
  \beta_L \leftarrow \frac{L_e}{p_{\text{emit}}}
  \]
- Eye path starts with unit importance.
- Camera connection uses `fluxToRadianceFactor` from camera PDF machinery.
- Segment throughput from `Scene::Intersect()` includes:
  - medium transmittance,
  - pass-through transparency,
  - shadow transparency where enabled.

**Approximations / bias risks**
- **Variance clamping** (`path.clamping.variance.maxvalue`) is biased.
- **PhotonGI cache** injects cached caustic/indirect energy; not pure BDPT.
- **Shadow terminator avoidance** modifies BSDF energy.
- **Direct-light MIS disabled after shadow transparency** is heuristic.
- **Volume emission is only accumulated on traced path segments**, not on arbitrary BDPT connection shadow rays; this is not a full symmetric volumetric BDPT treatment.
- Parser alias `"bidirectional" -> BIDIRVMCPU` means “legacy bidirectional” is actually hybrid VCM-like.

**Energy / reciprocity hazards for Mitsuba**
- Reusing Lux formulas with Mitsuba’s raw `eval()/sample()/pdf()` APIs without unwrapping Lux conventions will double-apply factors and break energy.
- Omitting Lux’s adjoint correction when porting light tracing will break reciprocity.
- Mixing Lux solid-angle PDFs with Mitsuba area PDFs without explicit conversion will break MIS.

---

## Mapping to Mitsuba 3

**Direct mapping**
- Lux render engine → Mitsuba custom `Integrator`
- `PathVertexVM` → custom vertex struct with:
  - interaction,
  - throughput/beta,
  - forward pdf,
  - reverse pdf,
  - delta flag,
  - depth,
  - emitter/light id,
  - medium state,
  - Lux MIS recurrence state (`dVCM`, optional `dVM`)
- Lux `BSDF` → Mitsuba `BSDF`
- Lux lights → Mitsuba `Emitter`
- Lux camera → Mitsuba `Sensor`
- Lux sampler → Mitsuba `Sampler`

**What can be reused**
- Scene intersection
- BSDF sampling/evaluation/pdf
- Emitter sampling/evaluation
- Sensor ray generation / sensor-direction queries
- Medium transmittance APIs

**What must be reimplemented**
- Explicit light subpath generation
- Explicit eye/light connection operators
- Sensor connection from light paths
- Georgiev-style MIS recurrences
- Lux-compatible depth semantics
- Optional VCM hash grid if `BIDIRVMCPU` parity is required

**Gaps / incompatibilities**
- Lux BSDF wrapper returns weighted values; Mitsuba generally exposes raw values.
- Lux tracks forward/reverse PDFs explicitly; Mitsuba may require recomputation.
- Lux camera provides `fluxToRadianceFactor`; Mitsuba sensor importance API is different.
- Lux path volume priority stack has to be mapped to Mitsuba medium transitions or custom state.
- Transparent-shadow semantics are engine-specific.

---

## Minimal Port Plan

1. **Target `BIDIRCPU`, not `BIDIRVMCPU`**, for first parity pass.
2. **Disable biased extras** conceptually:
   - variance clamping,
   - PhotonGI cache,
   - shadow-terminator tweak if physical parity is preferred.
3. Implement a Mitsuba `PathVertex` with:
   - interaction,
   - beta,
   - pdfFwd/pdfRev,
   - delta flag,
   - depth,
   - `dVCM/dVC`.
4. Implement **light subpath tracing** from `Emitter::sample_ray`.
5. Implement **eye subpath tracing** from `Sensor::sample_ray`.
6. Implement the four BDPT operators:
   - direct emitter hit,
   - NEE,
   - connect-to-eye,
   - connect-vertices.
7. Reproduce Lux MIS in the **same measure space**:
   - solid angle for local extensions,
   - area for endpoint alternatives.
8. Validate on minimal scenes:
   - diffuse area light,
   - point/distant light,
   - environment light,
   - specular chain,
   - medium scattering scene.
9. Only if legacy Lux “bidirectional” parity is required, add:
   - `dVM`,
   - merge radius schedule,
   - hash-grid vertex merging (`BIDIRVMCPU`).

**Bottom line**
- The repository contains **explicit BDPT** (`BIDIRCPU`) and a **VCM-style hybrid** (`BIDIRVMCPU`).
- For Mitsuba 3, the safest port target is:
  - **pure `BIDIRCPU` transport logic**,
  - with Lux’s BSDF/camera/light weighting conventions carefully translated,
  - and hybrid/biased extras added only afterward if needed.
