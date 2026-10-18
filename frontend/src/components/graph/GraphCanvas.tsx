import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraphMethods, type LinkObject, type NodeObject } from "react-force-graph-3d";
import { BoxGeometry, CanvasTexture, Group, Mesh, MeshStandardMaterial, OctahedronGeometry, SphereGeometry, Sprite, SpriteMaterial } from "three";
import type { EvidenceGraph, GraphLink, GraphNode, GraphSelection } from "../../types/graph";

type VisualLink = Omit<GraphLink, "source" | "target">;
const endpoint = (value: string | number | NodeObject<GraphNode> | undefined) => typeof value === "object" ? value.id : value;
const colors = { file: "#e1dcc9", commit: "#bd9569", person: "#8f7962" };

export default function GraphCanvas({ graph, selection, onSelect, resetToken, focusToken, onFailure }: {
  graph: EvidenceGraph; selection: GraphSelection; onSelect: (value: GraphSelection) => void; resetToken: number; focusToken: number; onFailure: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<ForceGraphMethods<GraphNode, VisualLink>>();
  const [size, setSize] = useState({ width: 0, height: 500 });
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [hovered, setHovered] = useState<string | null>(null);
  const fitted = useRef(false);
  // The graph engine mutates node positions and link endpoints. Never pass the evidence model itself.
  const data = useMemo(() => ({ nodes: graph.nodes.map((node, i) => ({ ...node, x: Math.cos(i * 2.4) * (30 + i * 3), y: Math.sin(i * 2.4) * (30 + i * 3), z: Math.sin(i * 1.2) * 35 })), links: graph.links.map(link => ({ ...link })) }), [graph.nodes, graph.links]);
  const objects = useRef(new Map<string, Group>());
  const highlighted = useMemo(() => {
    const ids = new Set<string>();
    if (selection?.type === "node") ids.add(selection.id);
    graph.links.forEach(link => {
      if (selection?.type === "link" ? link.id === selection.id : selection && (link.source === selection.id || link.target === selection.id)) { ids.add(link.source); ids.add(link.target); }
    });
    return ids;
  }, [selection, graph.links]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    const observer = new ResizeObserver(entries => { const rect = entries[0].contentRect; setSize({ width: Math.floor(rect.width), height: Math.floor(rect.height) }); });
    if (host.current) observer.observe(host.current);
    return () => { observer.disconnect(); media.removeEventListener("change", update); };
  }, []);

  useEffect(() => {
    if (!size.width) return;
    const canvas = host.current?.querySelector("canvas");
    const lost = (event: Event) => { event.preventDefault(); onFailure(); };
    const visibility = () => { if (document.hidden) api.current?.pauseAnimation(); else api.current?.resumeAnimation(); };
    canvas?.addEventListener("webglcontextlost", lost);
    document.addEventListener("visibilitychange", visibility);
    return () => { canvas?.removeEventListener("webglcontextlost", lost); document.removeEventListener("visibilitychange", visibility); };
  }, [size.width, onFailure]);

  useEffect(() => { fitted.current = false; }, [data]);
  useEffect(() => { if (resetToken) api.current?.zoomToFit(reduced ? 0 : 450, 65); }, [resetToken, reduced]);
  useEffect(() => {
    if (!focusToken || !selection) return;
    api.current?.zoomToFit(reduced ? 0 : 450, 100, node => highlighted.has(node.id));
    // Focus is an explicit action; changing selection alone does not move the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusToken]);

  const nodeObject = useCallback((node: NodeObject<GraphNode>) => {
    let group = objects.current.get(node.id);
    if (!group) {
      group = new Group();
      const geometry = node.kind === "file" ? new BoxGeometry(6, 7.5, 3) : node.kind === "commit" ? new OctahedronGeometry(4.2) : new SphereGeometry(4, 16, 12);
      const material = new MeshStandardMaterial({ color: colors[node.kind], roughness: .55, metalness: .15, transparent: true });
      group.add(new Mesh(geometry, material));
      const canvas = document.createElement("canvas");
      canvas.width = 512; canvas.height = 64;
      const context = canvas.getContext("2d");
      if (context) {
        context.font = "24px sans-serif"; context.fillStyle = "#e1dcc9"; context.textAlign = "center";
        context.fillText(node.label.length > 32 ? `${node.label.slice(0, 29)}…` : node.label, 256, 36);
        const sprite = new Sprite(new SpriteMaterial({ map: new CanvasTexture(canvas), transparent: true, depthTest: false }));
        sprite.scale.set(65, 8, 1); sprite.position.set(0, -10, 0); group.add(sprite);
      }
      objects.current.set(node.id, group);
    }
    return group;
  }, []);

  useEffect(() => {
    const map = objects.current;
    return () => {
      for (const group of map.values()) group.traverse(object => {
        if (object instanceof Mesh) { object.geometry.dispose(); (object.material as MeshStandardMaterial).dispose(); }
        if (object instanceof Sprite) { object.material.map?.dispose(); object.material.dispose(); }
      });
      map.clear();
    };
  }, []);

  useEffect(() => {
    for (const [id, group] of objects.current) {
      const active = !selection || highlighted.has(id);
      const mesh = group.children[0] as Mesh;
      const material = mesh.material as MeshStandardMaterial;
      material.opacity = active ? 1 : .17;
      material.emissive.set(selection?.id === id ? "#412d15" : "#000000");
      const sprite = group.children[1];
      if (sprite) sprite.visible = (graph.nodes.length <= 18 && active) || highlighted.has(id) || hovered === id;
    }
  }, [selection, highlighted, hovered, graph.nodes.length, size.width]);

  const activeLink = (link: LinkObject<GraphNode, VisualLink>) => !selection || (selection.type === "link" ? link.id === selection.id : endpoint(link.source) === selection.id || endpoint(link.target) === selection.id);
  return <div ref={host} className="graph-canvas" aria-label="Interactive 3D evidence graph. Use List view for keyboard-accessible entities and relationships.">
    {size.width > 0 && <ForceGraph3D<GraphNode, VisualLink>
      ref={api} graphData={data} width={size.width} height={size.height} backgroundColor="#0c0a08" showNavInfo={false} controlType="orbit"
      nodeThreeObject={nodeObject} nodeLabel={() => ""} linkLabel={() => ""}
      linkColor={link => activeLink(link) ? "#b59b7c" : "#332b21"} linkOpacity={.65} linkWidth={link => activeLink(link) && selection ? 1.2 : .45}
      linkDirectionalArrowLength={2.3} linkDirectionalArrowRelPos={.8} linkDirectionalArrowColor={link => activeLink(link) ? "#e1dcc9" : "#332b21"}
      onNodeClick={node => onSelect({ type: "node", id: node.id })} onNodeHover={node => setHovered(node?.id ?? null)}
      onLinkClick={link => onSelect({ type: "link", id: link.id })} onBackgroundClick={() => onSelect(null)}
      warmupTicks={reduced ? 90 : 35} cooldownTicks={reduced ? 0 : 90} cooldownTime={reduced ? 0 : 1800}
      onEngineStop={() => { if (!fitted.current) { api.current?.zoomToFit(reduced ? 0 : 450, 65); fitted.current = true; } }}
      enableNodeDrag={!reduced}
    />}
    <div className="canvas-caption" aria-hidden="true"><span className="canvas-cross">+</span> QUERY-SCOPED RELATIONSHIPS <span className="canvas-cross">+</span></div>
    {hovered && <div className="graph-tooltip">{graph.nodes.find(node => node.id === hovered)?.value}</div>}
    <div className="canvas-instructions">Drag to rotate <span>·</span> Scroll to zoom <span>·</span> Right-drag to pan</div>
  </div>;
}
