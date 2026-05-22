# Design Specification: AI Interviewer Agent ("Aura")

## Visual Identity & Aesthetic
Create a modern, futuristic, and professional UI for an "AI Interviewer Agent" named **Aura**. The design should follow the **"Linear Aesthetic"**—dark mode, high-contrast typography, and layered depth.

### Core Visual Element: The Agent Presence
- **Concept:** An abstract, organic entity rather than a human avatar. 
- **Style:** A "Liquid Orb" or "Dynamic Halo."
- **Behavior:** 
  - **Idle:** A soft, breathing indigo glow.
  - **Listening:** Surface ripples that respond to the user's voice frequency.
  - **Thinking:** A central swirling light pattern, simulating neural processing.
  - **Speaking:** Energetic expansion with concentric rings pulsing in sync with the audio.

### Color Palette
- **Base:** `#09090b` (Deep Space Black)
- **Primary Accent:** `#6366f1` (Indigo Glow) - used for the Agent and primary actions.
- **Secondary Accent:** `#10b981` (Emerald) - for "Interview Complete" or "High Performance" markers.
- **Surfaces:** Glassmorphic cards with `backdrop-filter: blur(12px)` and `#ffffff10` (10% white) background.
- **Borders:** 1px solid `#27272a` (Zinc-800) with occasional subtle linear-gradient glows.

### Typography
- **Headings:** Geist Sans or Inter (Bold, tight letter-spacing).
- **Body:** Inter (Medium/Regular).
- **Metadata:** JetBrains Mono (for timestamps and technical status).

---

## 1. Landing Page Prompt
**Goal:** High-conversion, minimalist SaaS landing page that communicates "The Future of Hiring."

- **Hero Section:**
  - **Headline:** "The First Interview, Automated by Intelligence."
  - **Subheadline:** "Scale your hiring with Aura. Real-time voice interviews that probe deeper, evaluate fairer, and report faster."
  - **CTA:** "Start a Mock Interview" (Primary) and "View Sample Report" (Secondary).
  - **Visual:** A high-fidelity 3D render of the "Aura Orb" floating in space with light streaks.
- **Feature Grid (Bento Style):**
  - **Resume Intelligence:** "Upload any PDF. Aura builds a custom interview rubric in seconds."
  - **Low-Latency Voice:** "Zero lag. Natural conversations powered by LiveKit and native LLMs."
  - **In-Depth Reporting:** "Objective, structured data on every candidate. No more bias, just performance."
- **Social Proof/Status:** "Built on LiveKit & Pydantic AI."

---

## 2. Interview Arena (Main App)
- **Central Visual:** Large, centered "Aura Orb" visualizer that reacts to voice.
- **Bottom-floating "Action Dock":** Frosted glass bar containing [Mute], [End Interview], and [Settings].
- **Right-aligned "Live Feed":** A minimalist, semi-transparent scrolling transcript using glassmorphism.
- **Top Indicator:** "Session Status: Active" with a subtle blinking recording dot.

---

## 3. Result Dashboard (Bento Grid)
- **Main Tile (2x2):** "Executive Summary" with a high-fidelity gauge showing the overall score.
- **Side Tile (1x2):** "Key Metrics" (Confidence, Clarity, Technical Depth) using small progress bars.
- **Bottom Tile (3x1):** "Timeline" - An interactive waveform of the interview with clickable transcript snippets.

---

## Recommended Design Tools
To create or iterate on these designs, use these "Open" or highly accessible tools:
1. **v0.dev:** Excellent for generating Shadcn/Tailwind components from text prompts.
2. **Figma:** Use "Community" templates for "SaaS Landing Pages" or "AI Dashboards" to start.
3. **Spline:** For creating the interactive 3D "Orb" visualizer.
4. **Bolt.new / Lovable:** For rapid prototyping of the entire landing page and interface.
5. **Tailwind UI / Magic UI:** For high-end, pre-built animated components (e.g., Marquee, Border Beam).

### Key Keywords for UI Builders
> "Minimalist AI dashboard, glassmorphism, bento grid layout, dark mode, indigo neon accents, organic 3D spheres, fluid motion, high-end SaaS aesthetic, Inter font, depth and shadows, futuristic voice interface."
