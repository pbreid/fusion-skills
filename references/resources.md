# Sources and further learning

The rules in this skill were distilled from these. Use them when you need more depth; prefer
official Autodesk documentation for API and feature behaviour.

## Official Autodesk
- Fusion MCP servers overview & setup - help.autodesk.com/view/ADSKMCP/ENU (Fusion MCP,
  Fusion Data MCP, Fusion Compute MCP, Product Help MCP)
- "Build Your Own Fusion Add-ins with the Fusion MCP" (Fusion blog, June 2026) - setup on port
  27182 and agent best practices (MVP first, test performance early, one correction at a
  time, screenshots as requirements, test via MCP, save first)
- "Autodesk Fusion Compute MCP: Public Beta" (Fusion blog, Sept 2026)
- Reference MCP add-in: github.com/AutodeskFusion360/FusionMCPSample
- Fusion API reference & user manual (Units, Configurations, Mesh, Sketch, Features) -
  help.autodesk.com/view/fusion360/ENU (Programming Interface section)
- "Sketching and Parametric Basics in Autodesk Fusion" (Fusion blog, May 2026)
- "Fusion 360 - Modeling Tips from the Experts", AU2016 PD20709, Peter Doering & Jeff Strater
  (Rule #1, sketch tips, reference stability, warnings vs errors, Compute All, repair of projections)
- AU classes: "Fusion 360 Assemblies Master Class" (Mike Prom - top-down,
  skeleton, positions), "Fusion 360 Workflows: Top Down vs Bottom Up", "Fusion Constraints
  Quick Start" (2025)
- Fusion blog: Top-down vs bottom-up modelling; Mastering Fusion parameters; Configurations
  overview; Joints vs constraints; Generate Face Groups; Convert Mesh to solid; Mastering STL
  meshes; Mirror/pattern compute options
- Fusion help: Mesh > Convert Mesh, Generate Face Groups; Sketch > Fit Curves to Mesh Section

## General CAD robustness
- Onshape, *Mastering 3D Modeling* ebook (anatomy of a robust model, sketch vs feature
  fillets, design intent via constraints)
- Parametric design-intent guidance (fully constrained sketches, feature tree in design
  order, flex-testing)

## Mesh reverse engineering (agent-side tooling ideas)
- trimesh (sections, facets, proximity, ICP) - used by scripts/
- build123d "Reconstructing a Design from an STL" tutorial and `detect_primitives`
- breptile (STL -> STEP with analytic planes/cylinders/spheres)
- Community skills that rebuild STL as OpenSCAD via section analysis (same idea, different kernel)

## Community MCP servers (fallbacks)
faust-machines/fusion360-mcp-server, prim-design/fusion-mcp, AuraFriday/Fusion-360-MCP-Server,
hitsmaxft/fusion-mcp-client (client + skill for the official endpoint), Joe-Spencer/fusion-mcp-server.

## DFM / printing
- Plastic enclosure DFM (wall 1.2-3 mm, draft 0.5-3 deg, ribs 40-60 % wall, bosses ~2-2.5x
  screw dia) - Fabcon summaries of Fictiv/Protolabs/Rex Plastics guidance
- FDM clearances and insert sizing - university fab-lab guides (UAL CCI), JLC3DP design guide,
  printer-vendor tolerance guides; always calibrate with a test coupon

## People to learn from (YouTube, for humans on the team)
- Product Design Online (Kevin Kennedy) - structured, current, beginner to advanced
- Tyler Beck - TECH ESPRESSO - 3D-printing-oriented Fusion workflows, quick tips
- Lars Christensen - deep explanations (older UI, principles still valid)
- Autodesk Fusion official channel (Fusion Live / Tips & Tricks, e.g. Brad Tallis)
- Justin Geis, Winston Moy (CAM), NYC CNC (machining)
