/*
 * The three package publishes runtime ESM in the lockfile; this frontend uses
 * only this small, stable surface. Keep these declarations limited to the
 * APIs the graph renderer calls.
 */
declare module "three" {
  export class Object3D {
    children: Object3D[];
    visible: boolean;
    position: { set(x: number, y: number, z: number): void };
    scale: { set(x: number, y: number, z: number): void };
    traverse(callback: (object: Object3D) => void): void;
    add(...objects: Object3D[]): this;
  }
  export class Light extends Object3D {}
  export class Scene extends Object3D {}
  export class Camera extends Object3D {}
  export class WebGLRenderer {}
  export class Geometry { dispose(): void }
  export class Color { set(value: string): this }
  export class Material { opacity: number; transparent: boolean; map?: CanvasTexture | null; dispose(): void }
  export class MeshStandardMaterial extends Material {
    emissive: Color;
    constructor(options: { color: string; roughness: number; metalness: number; transparent: boolean });
  }
  export class SpriteMaterial extends Material {
    constructor(options: { map?: CanvasTexture; transparent?: boolean; depthTest?: boolean });
  }
  export class BoxGeometry extends Geometry { constructor(width: number, height: number, depth: number) }
  export class OctahedronGeometry extends Geometry { constructor(radius: number) }
  export class SphereGeometry extends Geometry { constructor(radius: number, widthSegments?: number, heightSegments?: number) }
  export class Group extends Object3D {}
  export class Mesh extends Object3D { geometry: Geometry; material: Material; constructor(geometry: Geometry, material: Material) }
  export class Sprite extends Object3D { material: SpriteMaterial; constructor(material?: SpriteMaterial) }
  export class CanvasTexture { constructor(canvas: HTMLCanvasElement); dispose(): void }
}

declare module "three/examples/jsm/postprocessing/EffectComposer.js" {
  export class EffectComposer {}
}
