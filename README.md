# Confluence — Multi-Utility Analytics Dashboard

Confluence is the **Visualisation Layer** prototype for the *"Real-Time Multi-Utility Analytics with Explainable Anomaly Detection"* dissertation project. It is a client-side simulation of a live electricity / gas / water monitoring platform, built to demonstrate the dashboard's UX, alerting logic, and explainability panels described in the proposal's five-layer architecture — without requiring the backend (Kafka, TimescaleDB, ML services) to be running.

**Live demo:** deployed via GitHub Pages — see the repository's **About** section for the current URL once Pages is enabled.

## What it demonstrates

| Dissertation concept | Where it lives in this app |
|---|---|
| Live multi-utility monitoring (electricity 15-min, gas hourly, water variable-interval) | `Overview` and `Utilities` views — simulated diurnal consumption curves with Gaussian noise |
| Anomaly detection (rolling z-score on residuals) | `app.js` `tickUtility()` — flags points where the residual from the expected baseline exceeds a z-score threshold |
| Explainable AI (SHAP/LIME-style attribution) | `Alerts & XAI` view — clicking an alert renders a per-feature contribution breakdown (consumption deviation, rate of change, time-of-day deviation, historical volatility, cross-meter correlation) |
| Evaluation framework (Precision / Recall / F1 / ROC-AUC, latency vs. 2.5s target) | `Model Comparison` view — Z-score vs. Isolation Forest vs. LSTM Autoencoder+SHAP, with an annotated 2.5s latency threshold line |
| Five-layer platform architecture | `Architecture` view — Data Sources → Ingestion → Storage → Detection → Visualisation, with "you are here" on the Visualisation layer |

## Tech stack

![Tools and technology stack used in Confluence, showing implemented components (structure & styling, data visualisation, typography, dev & QA, version control & hosting) versus the dissertation's target platform architecture (data sources, ingestion, storage, detection) that is not yet wired up](docs/tools-diagram.svg)

Summary:

- **Structure & logic:** HTML5, CSS3 (custom properties, CSS Grid/Flexbox, light & dark themes), vanilla JavaScript (ES2020+, no framework, no build step)
- **Data visualisation:** [Chart.js](https://www.chartjs.org/) v4 + [chartjs-plugin-annotation](https://github.com/chartjs/chartjs-plugin-annotation) for the latency-threshold line
- **Typography:** [Fontshare](https://www.fontshare.com/) (Cabinet Grotesk, Satoshi) + [Google Fonts](https://fonts.google.com/) (JetBrains Mono)
- **Tooling:** Git/GitHub for version control, Playwright for visual QA during development, GitHub Pages for static hosting

No backend, database, or API keys are required — all data is generated client-side in `app.js` to model realistic diurnal utility-consumption patterns and inject anomalies at a controlled rate.

## Running locally

This is a static site with no build step.

```bash
git clone <this-repo-url>
cd confluence-dashboard
python3 -m http.server 8000
# open http://localhost:8000
```

Any static file server works (`npx serve`, VS Code Live Server, etc.) — the app just needs `index.html`, `style.css`, `base.css`, and `app.js` served together.

## Project structure

```
confluence-dashboard/
├── index.html      # Page shell, sidebar nav, 5 views (Overview, Utilities, Alerts & XAI, Model Comparison, Architecture)
├── style.css        # Design tokens, light/dark themes, component styles, responsive layout (incl. mobile bottom nav)
├── base.css         # Base reset / typography scale
├── app.js           # Data simulation, anomaly detection, alert + XAI generation, Chart.js wiring
├── assets/          # (reserved for static assets)
└── docs/
    └── tools-diagram.svg
```

## Deployment

The site is deployed via **GitHub Pages** directly from the repository — no build pipeline needed since it's static HTML/CSS/JS. To redeploy after edits, just push to `main`; Pages picks up the change automatically.

## Roadmap (per the dissertation's implementation milestone)

This prototype simulates the ingestion → storage → detection pipeline client-side to demonstrate the Visualisation Layer end-to-end. Wiring it to live Kafka topics, a TimescaleDB-backed API, and real SHAP/LIME output from the trained detection models is the next implementation milestone.
