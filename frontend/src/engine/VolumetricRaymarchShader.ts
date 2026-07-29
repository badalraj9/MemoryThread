import * as THREE from 'three'

export interface VolumetricShaderUniforms {
  uVolumeTexture: { value: THREE.Data3DTexture | null }
  uTime: { value: number }
  uCyanColor: { value: THREE.Color }
  uAmberColor: { value: THREE.Color }
  uStepCount: { value: number }
  uPulsePositions: { value: THREE.Vector3[] }
  uPulseTimes: { value: Float32Array }
  uPulseVelocities: { value: Float32Array }
  modelMatrixInverse: { value: THREE.Matrix4 }
}

export const volumetricVertexShader = `
  varying vec3 vLocalPosition;
  varying vec3 vWorldPosition;

  void main() {
    vLocalPosition = position / 800.0; // BoxGeometry(800) [-0.5, 0.5]
    vec4 worldPos = modelMatrix * vec4(position, 1.0);
    vWorldPosition = worldPos.xyz;
    gl_Position = projectionMatrix * viewMatrix * worldPos;
  }
`

export const volumetricFragmentShader = `
  varying vec3 vLocalPosition;
  varying vec3 vWorldPosition;

  uniform sampler3D uVolumeTexture;
  uniform float uTime;
  uniform vec3 uCyanColor;
  uniform vec3 uAmberColor;
  uniform int uStepCount;
  uniform mat4 modelMatrixInverse;

  // Signal Inputs (Max 8 concurrent recall shockwaves)
  uniform vec3 uPulsePositions[8];
  uniform float uPulseTimes[8];
  uniform float uPulseVelocities[8];

  // 3D Simplex-like noise for fluid boiling
  float hash(vec3 p) {
    p = fract(p * vec3(443.8975, 397.2973, 491.1871));
    p += dot(p.xyz, p.yzx + 19.19);
    return fract(p.x * p.y * p.z);
  }

  float noise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash(i + vec3(0,0,0)), hash(i + vec3(1,0,0)), f.x),
          mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
      mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
          mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
  }

  // Ray-Box Slab Intersection [0, 1]^3
  bool rayBoxIntersect(vec3 rayOrigin, vec3 rayDir, out float tNear, out float tFar) {
    vec3 invDir = 1.0 / max(abs(rayDir), vec3(0.0001)) * sign(rayDir);
    vec3 t0 = (vec3(0.0) - rayOrigin) * invDir;
    vec3 t1 = (vec3(1.0) - rayOrigin) * invDir;

    vec3 tMin = min(t0, t1);
    vec3 tMax = max(t0, t1);

    tNear = max(max(tMin.x, tMin.y), tMin.z);
    tFar  = min(min(tMax.x, tMax.y), tMax.z);

    return tNear < tFar && tFar > 0.0;
  }

  void main() {
    vec3 localCam = (modelMatrixInverse * vec4(cameraPosition, 1.0)).xyz / 800.0;
    vec3 rayOrigin = localCam + vec3(0.5);
    vec3 localPosUVW = vLocalPosition + vec3(0.5);
    vec3 rayDir = normalize(localPosUVW - rayOrigin);

    float tNear, tFar;
    if (!rayBoxIntersect(rayOrigin, rayDir, tNear, tFar)) {
      discard;
    }

    tNear = max(tNear, 0.0);
    float stepSize = (tFar - tNear) / float(uStepCount);
    vec3 currentPos = rayOrigin + rayDir * tNear;
    vec3 stepVec = rayDir * stepSize;

    vec4 accumulatedColor = vec4(0.0);

    for (int i = 0; i < 96; i++) {
      if (i >= uStepCount || accumulatedColor.a >= 0.95) break;

      if (any(greaterThan(currentPos, vec3(1.0))) || any(lessThan(currentPos, vec3(0.0)))) {
        currentPos += stepVec;
        continue;
      }

      vec4 texData = texture(uVolumeTexture, currentPos);
      float baseDensity = texData.r;
      float authority = texData.g;
      float corroboration = texData.b;
      float contradictionTear = texData.a;

      // Soft ambient bioluminescent breathing mist inside spherical orb boundary
      float distFromCenter = length(currentPos - vec3(0.5));
      float sphericalOrbMask = max(0.0, 1.0 - distFromCenter * 2.2);
      float ambientBioluminescence = noise(currentPos * 4.0 + uTime * 0.3) * 0.015 * sphericalOrbMask;

      float density = baseDensity + ambientBioluminescence;

      if (density > 0.001) {
        // --- SIGNAL LAYER: Analytical Recall Shockwaves ---
        float pulseSurge = 0.0;
        for (int p = 0; p < 8; p++) {
          float t0 = uPulseTimes[p];
          if (t0 > 0.0) {
            float deltaTime = uTime - t0;
            float dist = length(currentPos - (uPulsePositions[p] * 0.001 + vec3(0.5)));
            float waveFront = deltaTime * uPulseVelocities[p] * 0.15;

            float wavePacket = max(0.0, 1.0 - abs(dist - waveFront) / 0.08);
            float damping = exp(-1.2 * deltaTime);
            float oscillation = cos(35.0 * deltaTime - 100.0 * dist);

            pulseSurge += wavePacket * damping * max(0.0, oscillation) * 2.8;
          }
        }

        // --- CONTRADICTION TEAR HANDLING ---
        if (contradictionTear > 0.05) {
          float tearNoise = noise(currentPos * 25.0 + uTime * 3.5);
          density *= max(0.0, 1.0 - (contradictionTear * 2.5)) * tearNoise;
        }

        // Calibrated density step for soft translucent volumetric plasma
        float finalDensity = max(0.0, density) * stepSize * 2.2;

        // Sigmoid Non-Linear Color Interpolation
        float stability = authority * corroboration;
        float sigmoidWeight = 1.0 / (1.0 + exp(-10.0 * (stability - 0.5)));
        vec3 dynamicColor = mix(uCyanColor, uAmberColor, sigmoidWeight);

        // Blinding hyper-bright emission core glow at memory centers
        float coreGlow = pow(max(0.0, baseDensity * 1.5), 3.0) * 4.0;
        dynamicColor = (dynamicColor + vec3(coreGlow) * dynamicColor + vec3(pulseSurge) * uCyanColor * 2.0);

        // Translucent Beer-Lambert alpha compositing
        float alpha = (1.0 - exp(-finalDensity * 2.0)) * 0.35;
        vec4 stepColor = vec4(dynamicColor * alpha, alpha);

        // Additive front-to-back compositing
        accumulatedColor.rgb += stepColor.rgb * (1.0 - accumulatedColor.a);
        accumulatedColor.a += stepColor.a * (1.0 - accumulatedColor.a);
      }

      currentPos += stepVec;
    }

    if (accumulatedColor.a <= 0.001) {
      discard;
    }

    gl_FragColor = accumulatedColor;
  }
`

export function createVolumetricShaderMaterial(): THREE.ShaderMaterial {
  const uniforms: VolumetricShaderUniforms = {
    uVolumeTexture: { value: null },
    uTime: { value: 0 },
    uCyanColor: { value: new THREE.Color('#00f3ff') },
    uAmberColor: { value: new THREE.Color('#ffaa00') },
    uStepCount: { value: 96 },
    uPulsePositions: { value: Array.from({ length: 8 }, () => new THREE.Vector3()) },
    uPulseTimes: { value: new Float32Array(8).fill(-100) },
    uPulseVelocities: { value: new Float32Array(8).fill(1.0) },
    modelMatrixInverse: { value: new THREE.Matrix4() },
  }

  return new THREE.ShaderMaterial({
    uniforms: uniforms as unknown as { [uniform: string]: THREE.IUniform },
    vertexShader: volumetricVertexShader,
    fragmentShader: volumetricFragmentShader,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
}
