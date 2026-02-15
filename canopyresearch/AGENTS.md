# Canopy Research – Conceptual Modules Overview

Canopy Research is a **personal research radar**: a tool to explore, monitor, and analyze emerging topics across research domains (workspaces). The system emphasizes **structured exploration**, **signal detection**, and **cluster visualization** rather than simply surfacing raw content.

All modules are **workspace-scoped**, and the architecture is designed for **modular, testable units**.

---

## 1. Workspace Management

**Purpose:** Represent research domains and isolate data.

**Django Components:**

- **Models**
  - Workspace (name, description, core centroid, owner)
  - Source (RSS feed, HackerNews, Subreddit)
- **Views / Templates**
  - Workspace list & switcher
  - Workspace settings / core management
- **Background Tasks**
  - Workspace-level maintenance (e.g., cluster pruning, embedding refresh)

**UI Notes**

- Workspace switcher implemented as a Shoelace `<sl-select>` or similar component.
- Layout of workspace panels (metrics, map, sidebars) uses Shoelace grid / card components for consistency and visual clarity.

---

## 2. Data Ingestion

**Purpose:** Fetch content from multiple sources and normalize it into **Document** records.

**Django Components:**

- **Models**
  - Document (title, URL, content, source, publication date)
- **Services / Classes**
  - RSSIngestor
  - HackerNewsIngestor
  - SubredditIngestor
  - Document normalization logic
- **Background Tasks**
  - Periodic fetching
  - Error handling & source health logging

**UI Notes**

- Shoelace cards (`<sl-card>`) can optionally display ingestion progress, last fetched time, and source health on the source management page.

---

## 3. Document Processing

**Purpose:** Transform raw documents into structured data and compute metrics.

**Django Components:**

- Services:
  - Content extraction
  - Embedding computation (local or external)
  - Alignment scoring (relative to workspace core)
  - Novelty / velocity scoring
- Background Tasks:
  - Embedding recomputation
  - Cluster metric updates

**UI Notes**

- Display key document metrics in Shoelace tables or cards.
- Use `<sl-badge>` or `<sl-tag>` components to highlight high-velocity or high-alignment documents.

---

## 4. Clustering

**Purpose:** Organize documents into clusters per workspace.

**Django Components:**

- Models:
  - Cluster (documents, size, alignment, velocity)
- Services:
  - Cluster assignment logic
  - Cluster drift tracking
  - Metric updates
- Background Tasks:
  - Periodic cluster recomputation
  - Optional subcluster creation for emerging topics

**UI Notes**

- Cluster map visualization uses a JS `<cluster-map>` component fed from JSON endpoints.
- Clusters can be rendered in Shoelace cards when shown in list fallback.
- Metrics and cluster summaries use `<sl-badge>` or `<sl-card>` components.

---

## 5. Signals / Alerts

**Purpose:** Surface high-value clusters or documents.

**Django Components:**

- Models:
  - Signal (linked to document or cluster, score, timestamp)
- Services:
  - Signal scoring (alignment × growth × novelty)
- Background Tasks:
  - Periodic signal calculation
  - Optional digest generation

**UI Notes**

- Signals are displayed in Shoelace cards with clear scoring and cluster association.
- Optional digest view uses `<sl-card>` or `<sl-collapse>` to keep layout clean.

---

## 6. User Interface

**Purpose:** Enable structured exploration and inspection of research.

**Django Components:**

- Views / Templates:
  - Workspace switcher
  - Cluster map (JSON endpoint)
  - Cluster list fallback (HTMX)
  - Cluster detail side panel
  - Signals / alerts
  - Settings / source management
- Web Components / JS:
  - `<cluster-map>` (renders spatial cluster layout)
  - `<cluster-node>` (interactive nodes)
  - `<workspace-switcher>` (component for switching workspaces)
- HTMX:
  - Partial swaps for panels, tables, workspace switching
  - Minimal JS for non-map interactions

**UI Notes**

- **Shoelace components** are the foundation for layout: `<sl-grid>` for dashboard layout, `<sl-card>` for metrics and clusters, `<sl-tab>` for workspace tabs, `<sl-select>` for filters.
- Map and table layouts are flexible, but Shoelace ensures consistency and accessibility.
- Side panels and modals use `<sl-drawer>` or `<sl-dialog>`.

---

## 7. Maintenance / System Health

**Purpose:** Keep system data accurate, clean, and performant.

**Django Components:**

- Background Tasks:
  - Source health monitoring
  - Cluster cleanup & merge
  - Embedding refresh
  - Backup/export
- Admin / Settings:
  - Task logs
  - Source monitoring dashboards

**UI Notes**

- Shoelace badges and cards summarize source health and background task status.
- Optional visual alerts for failed ingestion jobs.

---

## Architectural Notes

- All modules are **workspace-scoped**.
- JSON endpoints feed the `<cluster-map>` component; other UI is server-rendered via HTMX.
- Embedding / processing modules are modular and swappable.
- No autonomous “agents”; all processes are deterministic background tasks and user actions.
- Shoelace provides consistent, modern, accessible layout across all views.