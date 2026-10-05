const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Footer, Header,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType, PageNumber,
  TableOfContents, PageBreak,
} = require('docx');

const REPO = '/home/user/workspace/confluence-dashboard';
const FIG = (f) => path.join(REPO, 'docs/figures', f);
const QA = (f) => path.join('/home/user/workspace/dissertation/img', f);
const FONT = 'Arial';
const TEXT_W = 9026; // A4 with 1-inch margins

// ---------- inline markup: **bold**, `code` ----------
function runs(text, opts = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|⟦[^⟧]+⟧)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...opts }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ ...opts, text: t.slice(2, -2), bold: true }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: 'Consolas', size: (opts.size || 22) - 2, ...opts, }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...opts }));
  return out;
}
const P = (t) => new Paragraph({ children: runs(t), spacing: { after: 160, line: 320 }, alignment: AlignmentType.JUSTIFIED });
const H1 = (t, br = true) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: br, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: 'bullets', level: 0 }, children: runs(t), spacing: { after: 80, line: 300 } });
const N = (t, ref) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 80, line: 300 } });

let figNo = 0, tabNo = 0;
const figIds = {}, tabIds = {};
function fig(id) { return `Figure ${figIds[id]}`; }
function tab(id) { return `Table ${tabIds[id]}`; }
// pre-register ids so text can reference before definition
const FIG_ORDER = ['arch', 'series', 'mon', 'cross', 'alerts', 'xai', 'study', 'f1auc', 'roc', 'util', 'types', 'h1', 'lat', 'cost'];
FIG_ORDER.forEach((k, i) => (figIds[k] = i + 1));
const TAB_ORDER = ['align', 'layers', 'data', 'anoms', 'ingest', 'schema', 'features', 'detectors', 'pages', 'levels', 'unit', 'defects', 'perf_setup',
  'metrics_def', 'latency', 'main', 'utilf1', 'h1', 'robust', 'xai', 'alerts', 'summary', 'outcomes', 'deploy'];
TAB_ORDER.forEach((k, i) => (tabIds[k] = i + 1));

function image(file, widthPx, caption, id, alt) {
  const buf = fs.readFileSync(file);
  // read png size
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const width = widthPx, height = Math.round((h / w) * widthPx);
  if (figIds[id] === undefined) throw new Error('unregistered fig ' + id);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: 'png', data: buf, transformation: { width, height },
        altText: { title: caption, description: alt || caption, name: id } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
      children: [new TextRun({ text: `Figure ${figIds[id]}: `, bold: true, size: 20 }), ...runs(caption, { size: 20 })] }),
  ];
}

const thin = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: thin, bottom: thin, left: thin, right: thin };
function table(id, caption, header, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const scale = TEXT_W / total;
  const W = widths.map((w) => Math.floor(w * scale));
  W[W.length - 1] += TEXT_W - W.reduce((a, b) => a + b, 0);
  const cell = (txt, i, isHead, rowIdx) => new TableCell({
    borders, width: { size: W[i], type: WidthType.DXA },
    shading: isHead ? { fill: 'E4EEEE', type: ShadingType.CLEAR } : (opts.highlight && opts.highlight(rowIdx) ? { fill: 'FBF3DD', type: ShadingType.CLEAR } : undefined),
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(txt).split('\n').map((line) => new Paragraph({
      alignment: (!isHead && i > 0 && opts.numeric !== false && /^[-+−]?[\d.,]+%?( ?±.*)?$|^[-+−]?[\d.]+ ?(s|ms|µs|min)?$/.test(line.replace(/\*\*/g, '').trim())) ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: runs(line, { size: 18, bold: isHead || undefined }) })),
  });
  if (tabIds[id] === undefined) throw new Error('unregistered tab ' + id);
  return [
    new Paragraph({ spacing: { before: 160, after: 80 }, keepNext: true,
      children: [new TextRun({ text: `Table ${tabIds[id]}: `, bold: true, size: 20 }), ...runs(caption, { size: 20 })] }),
    new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: W,
      rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, ri)) }))] }),
    new Paragraph({ spacing: { after: 200 }, children: [] }),
  ];
}

// ======================= CONTENT =======================
const C = [];
const add = (...xs) => xs.flat().forEach((x) => C.push(x));

// ---- title block
add(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 120 }, children: [new TextRun({ text: '7CS077 Dissertation — Submission 14.7', size: 22, color: '595959' })] }));
add(new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: 'Design and Evaluation of a Real-Time Analytics Platform for Monitoring Multi-Utility Networks Using Smart Meter Data and Anomaly Detection', bold: true, size: 36 })] }));
add(new Paragraph({ spacing: { after: 360 }, children: [new TextRun({ text: 'Chapters 4–6: Implementation, Testing and Results', size: 26 })] }));
add(P('This submission reports what was actually built, how it was tested and what it produced. Every number in Chapters 5 and 6 was generated by the implemented artefact; the code, raw outputs and the scripts that produce each table and figure are in the project repository (github.com/wez234/confluence-dashboard, folders `reports/` and `docs/figures/`). Where a result is not yet available — the operator study for H3 — this is stated rather than estimated.'));

// ======================= 4 IMPLEMENTATION =======================
add(H1('4. Implementation'));
add(P('Following the Design Science Research process (Hevner et al., 2004; Peffers et al., 2007), this chapter describes the design and development activity: the artefact that was built to answer RQ1 and to provide the experimental vehicle for RQ2 and RQ3. The platform, called Confluence, is written in Python 3 (about 4,200 lines across the `src/confluence` package, the Streamlit dashboard and the test suite). Section 4.1 presents the architecture as built; Sections 4.2 to 4.6 follow a reading from the meter to the operator\'s screen.'));
add(P('The work followed the six DSR activities of Peffers et al. (2007). **Problem identification and motivation** are covered in Chapters 1–2. **Objectives of a solution** were made explicit as a requirements specification of 29 functional and 13 non-functional requirements, each traced to a research question, hypothesis, outcome or ethical commitment (`docs/REQUIREMENTS.md` in the repository). **Design and development** are reported in this chapter. **Demonstration** was carried out by replaying the held-out test period through the live Kafka pipeline and the dashboard (Sections 5.3 and 6.4). **Evaluation** is reported in Chapters 5 and 6, and **communication** is through this thesis and the public code repository.'));
add(P(`${tab('align')} checks the artefact against each commitment made in the proposal, so that any deviation is visible and justified rather than hidden.`));
add(table('align', 'Alignment of the implemented artefact with the proposal', ['Proposal commitment (section)', 'As implemented', 'Reported in', 'Status'], [
  ['Five-layer architecture (3.1)', 'Data sources, Kafka ingestion, PostgreSQL/TimescaleDB storage, detection engine, Streamlit dashboard, plus cross-cutting services', '4.1', 'Implemented'],
  ['Kappa, not Lambda; no serverless (3.2)', 'Single streaming code path shared by training, replay and live processing', '4.1', 'Implemented as proposed'],
  ['SGCC, UK smart-meter and simulated water data (3.1)', 'Synthetic labelled data for all three utilities used in experiments; SGCC and London smart-meter adapters implemented and tested', '4.2.1', 'Deviation: public data lack anomaly labels'],
  ['Heterogeneous frequencies and timestamp normalisation (3.1)', '15-min electricity, hourly gas, irregular local-time water normalised to UTC grids', '4.2.3', 'Implemented'],
  ['Kafka ingestion with validation and cleansing (3.1)', 'Producer, consumer group, micro-batch stream processor', '4.3', 'Implemented'],
  ['TimescaleDB/PostgreSQL partitioned tables (3.1)', 'Hypertables, continuous aggregate, compression, retention; measured on PostgreSQL 16', '4.4', 'Implemented; extension not benchmarked'],
  ['Z-score, Isolation Forest, LSTM autoencoder (3.1)', 'All three, plus moving average, One-Class SVM, weighted ensemble and an offline STL comparator', '4.5', 'Implemented and extended'],
  ['SHAP/LIME explainability (3.1)', 'TreeSHAP on every streamed alert, LIME and KernelSHAP on demand, plain-language narrative', '4.5.5', 'Implemented'],
  ['Dashboard: live monitoring, history, explainable alerts (3.1)', 'Eight pages, including cross-utility, KPIs and user study', '4.6', 'Implemented'],
  ['Precision, recall, F1, ROC-AUC, latency, throughput, resources (3.3)', 'Held-out test period, three seeds, steady and stress Kafka runs', '5.3–5.4, 6.1–6.3', 'Completed'],
  ['SUS > 70, TAM, operator trust (3.3)', 'Study instrument and analysis built and tested', '6.4', 'Pending participants'],
  ['Ethics (3.4)', 'No PII; consent; monitoring only; operator-mediated thresholds; explanations with audit trail', '4.4–4.6', 'Implemented'],
  ['H1, H2, H3', 'Tested, tested, instrument ready', '6.3.3, 6.1, 6.4', 'H1 not supported; H2 supported; H3 pending'],
], [2.6, 3.4, 1.2, 1.8], { numeric: false }));

add(H2('4.1 System Architecture'));
add(P(`The implemented architecture is shown in ${fig('arch')}. It keeps the five layers of the proposal — data sources, ingestion, storage, detection and visualisation — and adds the cross-cutting services that the proposal\'s Figure 1 identified (monitoring and logging, alert management, security, an API layer, and backup and recovery). ${tab('layers')} maps each layer to the technology chosen and the module that implements it.`));
add(image(REPO + '/docs/architecture.png', 600, 'As-built system architecture of the Confluence platform (Kappa architecture). Solid arrows show data flow; the dashed arrow shows control and monitoring.', 'arch'));
add(table('layers', 'Architecture layers, technologies and implementing modules', ['Layer', 'Technology', 'Implementation (src/confluence/…)'], [
  ['1 Data sources', 'Synthetic generator (NumPy); SGCC and London smart-meter adapters', '`data/generator.py`, `data/sgcc.py`, `data/uk_lcl.py`'],
  ['2 Ingestion', 'Apache Kafka 3.9 (KRaft), kafka-python; validation, cleaning, UTC normalisation, features', '`ingestion/producer.py`, `consumer.py`, `stream_processor.py`, `validation.py`, `cleaning.py`, `normalise.py`, `features.py`'],
  ['3 Storage', 'PostgreSQL 16 with TimescaleDB hypertables, continuous aggregate, compression and retention', '`storage/schema.sql`, `storage/db.py`'],
  ['4 Detection', 'scikit-learn (Isolation Forest, One-Class SVM), PyTorch (LSTM autoencoder), SHAP, LIME', '`detection/`, `explain/`'],
  ['5 Visualisation', 'Streamlit, Plotly', '`dashboard/app.py`, `dashboard/views/`'],
  ['Cross-cutting', 'FastAPI REST layer; JSON logging; alert rules; pg_dump backup; Docker Compose', '`api/main.py`, `logging_setup.py`, `alerts/rules.py`, `ops/backup/backup.sh`, `docker-compose.yml`'],
], [1.4, 3.3, 4.3], { numeric: false }));
add(P('**Kappa rather than Lambda.** As argued in the proposal (Section 3.2), a single streaming path was implemented (Kreps, 2014). The same functions perform validation, cleaning, normalisation and feature extraction for the offline training run and for the live Kafka consumer; historical reprocessing is achieved by replaying the topic or the source files through the producer. This removed the main risk of a Lambda design — two implementations of the feature logic drifting apart — and the equivalence of the two paths is checked by an automated test (Section 5.2). Serverless functions were not used in the alert path because cold-start delays would threaten the 2.5-second latency target (H2), and the detectors need per-meter state (the previous 24 hours of readings) that suits a long-running consumer.'));
add(P('**Changes from the proposal.** Three changes were made during development, each for a stated reason. First, a 24-hour moving-average detector and a One-Class SVM were added so that each family (statistical, machine learning) has two members and the comparison in RQ2 does not rest on a single representative. Second, an ensemble with weighted voting was added because the proposal\'s Figure 1 included decision fusion. Third, a seasonal-trend decomposition (STL) detector was implemented as an **offline comparator** rather than inside the streaming engine, because STL is a centred smoother that needs future observations and therefore cannot score a reading at the moment it arrives (Section 4.5.6). The scope was deliberately kept to three utilities with comparable consumption signals — electricity, gas and water; other networks (for example fibre) were excluded because they lack an equivalent public consumption dataset.'));

add(H2('4.2 Data Sources and Preparation'));
add(H3('4.2.1 Choice of data'));
add(P('Two public datasets were identified in the proposal: the SGCC electricity-theft dataset (Zheng et al., 2018) and the London smart-meter dataset published by UK Power Networks (2014). Both are single-utility and neither carries point-level labels of when an anomaly occurs, so precision, recall and F1 — the core metrics of the evaluation framework — cannot be computed on them directly. The platform therefore uses a **synthetic multi-utility generator with injected, labelled anomalies** for all experiments, and provides adapters (`data/sgcc.py`, `data/uk_lcl.py`) so that the same pipeline can be run on the real datasets. This is a conscious trade-off: synthetic data give a ground truth for comparing methods, at the cost of external validity, which is discussed as a threat to validity in Section 6.5. It is also consistent with the ethics section of the proposal, since no personal or company data are processed; the industrial motivation comes from UK multi-utility operations, but no operator\'s internal data were used.'));
add(P(`The generator (${tab('data')}) produces 60 days (5 January – 5 March 2026, which spans no clock change; the separate DST test in Section 5.2 covers the March transition) for 10 meters per utility. Each meter index represents one property (site) with one meter of each utility, which enables the cross-utility analysis. Consumption follows diurnal and weekly profiles specific to each utility — morning and evening peaks for electricity, heating-driven peaks for gas, and short draw events for water — with per-meter scale and multiplicative noise.`));
add(table('data', 'Characteristics of the experimental dataset (seed 42)', ['Utility', 'Meters', 'Raw interval', 'Timestamps', 'Unit', 'Canonical rows'], [
  ['Electricity', '10', '15 min, regular', 'UTC', 'kWh per interval', '57,600'],
  ['Gas', '10', '60 min, regular', 'UTC', 'm³ per hour', '14,400'],
  ['Water', '10', '5–30 min, irregular', 'UK local time (Europe/London)', 'L/min', '57,599'],
  ['Total', '30', '', '', '', '129,599'],
], [1.3, 0.8, 1.6, 2.2, 1.6, 1.4]));
add(P(`Five anomaly types were injected, nine events per meter on average, with the shapes summarised in ${tab('anoms')}. Three of them — drift, leak and stuck meter — are sustained patterns and form the "temporal anomaly" group used to test H1. The anomaly rate is 3.3% of readings in the training period, 4.1% in validation and 3.3% in test.`));
add(table('anoms', 'Injected anomaly types', ['Type', 'Shape', 'Operational meaning', 'H1 group'], [
  ['Spike', 'Short multiplicative surge (1–3 readings)', 'Equipment fault, data burst', 'No'],
  ['Drop', 'Consumption falls to near zero', 'Outage, bypass or theft', 'No'],
  ['Leak', 'Elevated baseline, especially overnight', 'Water or gas leak', 'Yes'],
  ['Stuck', 'Identical value repeated', 'Meter or register fault', 'Yes'],
  ['Drift', 'Gradual ramp away from the profile', 'Calibration drift, slow fault', 'Yes'],
], [1, 2.6, 2.6, 0.9], { numeric: false }));
add(H3('4.2.2 Data-quality faults and cleaning'));
add(P(`To exercise the ingestion layer, the generator also injects the data-quality problems typical of meter feeds: duplicated readings, missing values, negative sentinel values (−1), and water timestamps reported in local time rather than UTC. ${tab('ingest')} reports what the pipeline found and repaired in the 121,817 raw records.`));
add(table('ingest', 'Validation and cleaning outcomes for the experimental dataset (measured)', ['Stage', 'Rule', 'Records affected'], [
  ['Validation', 'Schema, known utility, parseable timestamp, numeric value, plausibility ceiling', '121,345 valid; 472 missing values tagged for repair; 0 rejected'],
  ['Cleaning', 'Duplicate (meter, timestamp) pairs removed', '488'],
  ['Cleaning', 'Negative sentinels converted to missing', '100'],
  ['Cleaning', 'Missing values carried to normalisation', '569'],
  ['Normalisation', 'Convert to UTC; align to canonical grid; interpolate gaps of ≤ 2 steps and flag them', '129,599 grid rows; 15,298 interpolated (mostly water re-gridding)'],
], [1.3, 4.4, 3.3], { numeric: false }));
add(H3('4.2.3 Normalisation of heterogeneous frequencies'));
add(P('Electricity and gas already arrive on regular 15-minute and hourly grids. Water arrives irregularly in local time, so it is converted to UTC with the Europe/London rules (which correctly handle the spring and autumn clock changes), then binned to a 15-minute grid by mean, with short gaps interpolated and flagged so that they are never mistaken for genuine readings. For cross-utility analysis all three utilities are additionally aggregated to an hourly common axis.'));
add(H3('4.2.4 Experimental split'));
add(P('Data were split by time, never randomly, to avoid leaking future information: days 1–35 for training (fitting every detector and the consumption profiles), days 36–45 for validation (calibrating thresholds and ensemble weights, and selecting the LSTM configuration), and days 46–60 as the held-out test period, which is used only for the results in Chapter 6.'));
add(image(FIG('fig2_sample_series.png'), 600, 'Five test-period days for one meter of each utility: readings, the expected value learnt from training data, injected anomalies (shaded) and ensemble flags.', 'series'));
add(P(`${fig('series')} illustrates the prepared data and the detection output. The electricity meter shows overlapping drift and stuck-meter episodes followed by a drop to near zero; the gas meter shows a leak-like raised baseline; the water meter shows a short drop and then a leak episode. The dashed line is the profile-based expected value that later drives both the Z-score detector and the plain-language explanations.`));

add(H2('4.3 Streaming Data Pipeline'));
add(P('**Producer.** `ingestion/producer.py` replays readings in UTC order onto the Kafka topic `meter-readings-raw`. Each message is a JSON record (timestamp, meter, utility, value) keyed by meter ID, so that all readings of a meter go to the same partition and are processed in order by the same consumer. The producer stamps each message with its publication time (`produced_at`), which is the start point for latency measurement. Near-real-time behaviour is simulated by a configurable replay speed: at the default of 600× real time, one 15-minute interval is published every 1.5 seconds; the evaluation runs used 1,800×. A warm-up of 26 simulated hours is published first so that each meter\'s 24-hour baseline is populated before scoring.'));
add(P('**Consumer and stream processor.** `ingestion/consumer.py` (consumer group `confluence-analytics`) polls up to 200 records at a time and passes them to the `StreamProcessor`. For each record the processor runs the validation rules of Section 4.2.2, drops duplicates, converts the timestamp to UTC and the canonical grid, appends the reading to a per-meter ring buffer of the last 100 readings, recomputes the causal features for the new reading, scores it with all detectors and the ensemble, and — if the reading is flagged — computes a TreeSHAP explanation and a narrative. Processing is done in micro-batches (all records of a poll are scored together) because scoring one record at a time limited throughput to about 10 readings per second (Section 5.2, defect D4).'));
add(P('**Outputs.** Each processed micro-batch is written to PostgreSQL in a single transaction (raw readings, processed readings with features, scores and flags, and any anomalies with their explanations). Only after the commit is the latency recorded (`committed_at`), so the measured latency includes everything until an alert becomes visible to the dashboard and API. Alerts are also published to a second topic, `anomaly-alerts`, which allows downstream notification services to subscribe without touching the database.'));

add(H2('4.4 Data Storage and Processing'));
add(P(`Storage is a PostgreSQL 16 database with the TimescaleDB extension (${tab('schema')}). TimescaleDB was chosen because meter data are append-only, time-ordered and queried by time range; hypertables partition each table into time chunks so that recent-data queries touch only a few small partitions, compression reduces the footprint of older chunks, and a continuous aggregate maintains hourly totals incrementally for the historical and cross-utility views. Because it is a PostgreSQL extension, ordinary SQL, roles and backup tools continue to work, which matters for operator adoption (see ⟦docs/DEPLOYMENT.md⟧).`));
add(table('schema', 'Database schema (storage/schema.sql)', ['Object', 'Type', 'Purpose'], [
  ['raw_readings', 'Hypertable (1-day chunks); compression after 7 days; retention 400 days', 'Readings as received, after validation'],
  ['processed_readings', 'Hypertable (1-day chunks)', 'Features, per-detector scores and flags, ensemble score, latency stamps'],
  ['hourly_consumption', 'Continuous aggregate, refreshed every 15 min', 'Hourly common axis for historical and cross-utility analysis'],
  ['anomalies', 'Hypertable (7-day chunks)', 'Alerts: severity, votes, SHAP values, narrative, status'],
  ['audit_log, threshold_changes', 'Tables', 'Every operator action and threshold change, with actor and time'],
  ['study_responses', 'Table', 'Pseudonymous user-study responses'],
  ['confluence_ingest, confluence_readonly', 'Roles', 'Least-privilege access for the pipeline and the dashboard'],
], [2.3, 3.4, 3.3], { numeric: false }));
add(P('The schema loader detects whether the TimescaleDB extension is present. If it is not, the TimescaleDB-specific statements are skipped and the same tables are created as ordinary PostgreSQL tables. This fallback was needed in the development environment, where Docker (and therefore the TimescaleDB image) was not available; the integration measurements in Chapter 5 were made on plain PostgreSQL 16.4, which is stated wherever those results are reported. The dashboard can also run in a **demo mode** that reads the saved test-period results from Parquet files, so that the interface can be demonstrated and used in the user study without any infrastructure.'));

add(H2('4.5 Anomaly Detection Implementation'));
add(P(`Detection is performed by ⟦detection/engine.py⟧, which trains one set of detectors per utility because the three utilities differ in frequency and consumption pattern. All detectors consume the same eleven causal features (${tab('features')}) — causal meaning that each feature uses only the current and past readings, so the offline evaluation reproduces exactly what the streaming consumer can compute.`));
add(table('features', 'Feature set computed for every reading (ingestion/features.py)', ['Feature', 'Definition', 'Mainly targets'], [
  ['profile_z', '(value − median for this meter, hour and day type) ÷ robust scale (MAD), learnt on training data', 'Spikes, drops, leaks'],
  ['ma_z', 'Deviation from the previous 24 hours\' mean, in standard deviations', 'Level changes'],
  ['rate_of_change', 'Difference from the previous reading ÷ meter mean', 'Spikes, drops'],
  ['volatility', 'Rolling standard deviation over 8 readings ÷ meter mean', 'Noisy faults'],
  ['flat_run', 'Length of the current run of identical values (capped at 12)', 'Stuck meters'],
  ['min_level', 'Rolling minimum over 8 readings ÷ meter mean', 'Leaks (raised base load)'],
  ['cross_meter_z', 'Deviation from peer meters of the same utility at the same time', 'Meter-specific faults'],
  ['level', 'Value ÷ meter mean', 'General'],
  ['hour_sin, hour_cos, is_weekend', 'Cyclical time of day and day type (UK local time)', 'Context'],
], [1.8, 5.0, 2.2], { numeric: false }));
add(H3('4.5.1 Statistical detectors'));
add(P('**Z-score.** The score is the absolute value of `profile_z`: how many robust standard deviations the reading lies from the meter\'s typical value for that hour of day and day type. Using a per-hour profile rather than a global mean is what makes a statistical method usable on strongly seasonal consumption data. **Moving average.** The score is the absolute value of `ma_z`, the deviation from the trailing 24-hour mean, a standard short-memory baseline. Both have no training cost beyond the profile and are fully interpretable.'));
add(H3('4.5.2 Machine-learning detectors'));
add(P('**Isolation Forest** (Liu et al., 2008) isolates readings with random axis-parallel splits; anomalies need fewer splits. It was configured with 200 trees and 512 samples per tree and trained on all training readings; the anomaly score is the negated `score_samples`. **One-Class SVM** (Schölkopf et al., 2001) learns a boundary around normal data with an RBF kernel (ν = 0.05) on standardised features; it was trained on a random sample of 3,000 training readings per utility to keep fitting time and memory bounded.'));
add(H3('4.5.3 Deep-learning detector: LSTM autoencoder'));
add(P('An LSTM encoder–decoder autoencoder (Malhotra et al., 2016) was implemented in PyTorch (`detection/lstm_autoencoder.py`). It reads windows of 16 consecutive readings (4 hours of electricity or water, 16 hours of gas) of five inputs (profile deviation, level, rolling minimum and the cyclical hour), compresses them through an 8-unit LSTM bottleneck and reconstructs them; the anomaly score of a reading is the reconstruction error of the window that ends at it. Training uses up to 15,000 windows per utility for 12 epochs, after removing windows containing extreme profile deviations so that the model learns normal behaviour. The configuration was selected from five candidates on the validation period only (window of 16 or 32 steps, bottleneck of 8, 16 or 32 units, and three input sets); the narrow bottleneck was decisive because a wide autoencoder reconstructed level shifts too well to flag them.'));
add(H3('4.5.4 Threshold calibration and ensemble'));
add(P('Every detector produces a continuous score, and an operational threshold is calibrated on the validation period by maximising F1, subject to an **alert budget**: the threshold may never flag more than 15% of readings. The budget was introduced after an early run showed that the moving-average detector "won" F1 by flagging 99% of readings (Section 5.2, defect D2). The ensemble converts each detector\'s score into a percentile against its validation scores, so that scores on different scales become comparable, and averages the percentiles with weights proportional to each detector\'s validation F1 (weighted voting). A single ensemble threshold, calibrated in the same way, makes the decision (decision fusion). The number of detectors over their own threshold (`votes`) is retained and drives alert severity. Thresholds can be changed by an operator at run time from the dashboard or the API; every change is written to `threshold_changes`, and the system never changes them by itself.'));
add(table('detectors', 'Implemented detectors and ensemble weights (validation F1 share)', ['Detector', 'Family', 'Streaming', 'Weight: electricity / gas / water', 'Training time (electricity)'], [
  ['Z-score', 'Statistical', 'Yes', '0.25 / 0.28 / 0.24', '< 0.01 s (profile only)'],
  ['Moving average (24 h)', 'Statistical', 'Yes', '0.07 / 0.03 / 0.04', '< 0.01 s'],
  ['Isolation Forest', 'Machine learning', 'Yes', '0.24 / 0.22 / 0.23', '0.31 s'],
  ['One-Class SVM', 'Machine learning', 'Yes', '0.23 / 0.24 / 0.32', '0.03 s'],
  ['LSTM autoencoder', 'Deep learning', 'Yes', '0.20 / 0.22 / 0.17', '3.67 s (CPU)'],
  ['Ensemble', 'Fusion', 'Yes', '—', '—'],
  ['STL decomposition', 'Statistical', 'No (offline only)', 'not in ensemble', '52 s for all 30 meters'],
], [2.0, 1.5, 1.4, 2.4, 1.9], { numeric: false }));
add(H3('4.5.5 Explainability'));
add(P('Each alert raised in the stream receives a TreeSHAP explanation (Lundberg and Lee, 2017; Lundberg et al., 2020) computed exactly on the Isolation Forest, which costs a few milliseconds and therefore fits within the latency budget. On demand, LIME (Ribeiro et al., 2016) and KernelSHAP are computed on the tabular ensemble of the four feature-based detectors, so that the explanation reflects the combined decision rather than a single model. The LSTM reads windows rather than one feature vector and is not covered by these per-reading attributions; its vote is shown separately. `explain/narrative.py` turns the top attributions into an operator-language sentence that is aware of direction and utility (for example, "Main reason: the reading is far above what this meter normally uses at this time of day. Also contributing: consumption never drops back to its normal minimum — typical of a leak").'));
add(H3('4.5.6 STL comparator'));
add(P('To answer whether a classical decomposition method would perform better than the profile Z-score, STL (Cleveland et al., 1990) was implemented in `scripts/supplementary_experiments.py` using statsmodels. For each meter, the series is decomposed with a daily period (96 steps for 15-minute data, 24 for hourly) using the robust option; the score is the absolute residual divided by the residual\'s median absolute deviation on the training period, and the threshold is calibrated on the validation period with the same F1 and alert-budget rule. Because STL\'s loess smoothers are centred, a residual at time t depends on readings after t; STL therefore has an information advantage over the streaming detectors, yet cannot be deployed in the stream without a delay of at least half a smoothing window. It is reported as an offline comparator only.'));
add(H3('4.5.7 Alert management'));
add(P('Flagged readings are grouped into alert events per meter (`alerts/rules.py`). To reduce single-reading noise, an event is raised only if it spans at least two consecutive flagged readings, or if at least three detectors agree on a single reading. Severity is **critical** if four or more detectors agree, if the ensemble percentile exceeds 0.995 or if the event is long; **warning** if two or more detectors agree or the event lasts four readings; otherwise **info**. Unacknowledged alerts escalate after 30 minutes, and anomalies in two or more utilities at the same site within two hours are linked as a cross-utility event.'));

add(H2('4.6 Dashboard Implementation'));
add(P(`The dashboard is a multi-page Streamlit application (${tab('pages')}). When a database is configured, the monitoring page reads live readings, alerts with their narratives, and pipeline latency from the PostgreSQL tables written by the Kafka consumer. The analysis pages (historical, cross-utility, alerts, explainable AI and user study) read the stored results of the evaluation run, so that every participant and marker sees the same test period. Without a database, every page runs in demo mode, and the monitoring page replays the held-out test period: the scores and alerts are the trained models\' real outputs on unseen data, but the clock is simulated, which the page states.`));
add(table('pages', 'Dashboard pages and their purpose', ['Page', 'Content', 'Supports'], [
  ['Real-time monitoring', 'Play/replay clock, utility selection, KPIs (readings, alerts, critical, Kafka latency), per-utility charts with expected value and alert markers, alert feed with narratives', 'RQ1, RQ3'],
  ['Historical analysis', 'Any meter over the 60-day record with selectable detector flags, daily consumption and raw detector scores', 'RQ3'],
  ['Cross-utility comparison', 'Hourly index for the three meters of a site, correlation matrix, co-occurring alerts', 'RQ1'],
  ['Alerts and notifications', 'Queue with severity, status and votes; acknowledge, dismiss, escalate; threshold panel; audit trail', 'RQ3, ethics'],
  ['Model performance', 'Measured KPIs read from reports/: accuracy tables, latency, H1 and H2 status', 'RQ2'],
  ['Explainable AI', 'SHAP and LIME bar charts, narrative, context chart and detector votes for any alert', 'RQ3, H3'],
  ['User study', 'Consent, randomised XAI or black-box condition, eight alert tasks, trust, SUS and TAM questionnaires', 'RQ3, H3'],
  ['About and ethics', 'Data provenance, monitoring-only policy, limitations', 'Ethics'],
], [2.0, 5.4, 1.6], { numeric: false }));
add(P(`${fig('mon')} shows the monitoring page. The KPI row shows the simulated time, readings and alerts in the last 24 hours, critical alerts and the measured mean Kafka latency; each utility has its own chart at its native interval, with the expected value dashed and meters in alert marked, and the alert feed on the right gives severity, meter and the generated explanation.`));
add(image(QA('monitoring.png'), 600, 'Real-time monitoring page (demo mode, replaying the held-out test period).', 'mon'));
add(P(`The cross-utility page (${fig('cross')}) places the three meters of one site on the hourly common axis, shows the correlation between utilities over the whole record and lists co-occurring alerts. The alerts page (${fig('alerts')}) is where the operator acts: every acknowledgement, dismissal, escalation and threshold change is written to the audit trail with the operator\'s name, which implements the monitoring-only, operator-mediated policy of the ethics section.`));
add(image(QA('cross-utility.png'), 600, 'Cross-utility comparison for one site, with correlation matrix and co-occurring alerts.', 'cross'));
add(image(QA('alerts.png'), 600, 'Alert queue with severity, status, detector agreement and cross-utility linkage.', 'alerts'));
add(P(`${fig('xai')} shows the explainable-AI page for an alert: the narrative, the TreeSHAP attribution for the Isolation Forest, the LIME attribution for the ensemble, and the context chart with the votes of each detector. ${fig('study')} shows the start of the user-study flow, which collects informed consent before any task and stores responses only against a random participant code.`));
add(image(QA('explain.png'), 600, 'Explainable AI page: narrative, SHAP and LIME attributions for one alert.', 'xai'));
add(image(QA('study.png'), 560, 'User-study page: participant information and consent.', 'study'));
add(P('A FastAPI service (`api/main.py`) exposes the same data to other systems: `/readings`, `/anomalies`, `/metrics`, `/thresholds` and `/health`, plus two write endpoints, `/thresholds` and `/alerts/{id}/ack`, which require an API key and write to the audit tables.'));

// ======================= 5 TESTING =======================
add(H1('5. Testing'));
add(H2('5.1 Testing Strategy'));
add(P(`Testing was planned at four levels (${tab('levels')}), from individual functions to the behaviour of the whole pipeline under load, plus a separate experimental evaluation of the detectors. Automated tests run on every push to the repository through GitHub Actions, so that a change which breaks the pipeline is detected immediately; performance and detection tests are scripted so that every number in Chapter 6 can be reproduced with a single command (⟦python -m confluence.evaluation.run⟧).`));
add(table('levels', 'Test levels', ['Level', 'What is tested', 'How', 'Evidence'], [
  ['Unit', 'Validation, cleaning, normalisation, features, scoring, alert rules, SUS scoring', 'pytest (18 tests)', 'Section 5.2, CI log'],
  ['Integration', 'Stream processor against batch path; API against stored data; schema on PostgreSQL', 'pytest; manual run', 'Section 5.2'],
  ['System and performance', 'Producer → Kafka → consumer → database, steady and stress load', 'Scripted replay, latency log', 'Section 5.3, ' + tab('latency')],
  ['Acceptance (interface)', 'Every dashboard page renders and interactive controls work', 'Scripted browser screenshots and manual checks', 'Section 5.2, Figures ' + figIds.mon + '–' + figIds.study],
  ['Model evaluation', 'Detection accuracy, H1, explanation quality', 'Held-out test period, 3 seeds', 'Section 5.4, Chapter 6'],
], [1.6, 3.2, 2.2, 2.0], { numeric: false }));

add(H2('5.2 Functional Testing'));
add(P(`${tab('unit')} lists the automated tests and the requirement each verifies (requirement IDs refer to the requirements specification in ⟦docs/REQUIREMENTS.md⟧). All 18 tests pass locally and in continuous integration.`));
add(table('unit', 'Automated functional tests (tests/)', ['Test', 'Verifies', 'Req.', 'Result'], [
  ['test_generator_has_all_utilities_and_labels', 'All three utilities generated; every anomaly labelled with a type', 'FR-01', 'Pass'],
  ['test_validation_rejects_bad_records', 'Bad timestamp, unknown utility and non-numeric values rejected; missing values kept for repair', 'FR-04', 'Pass'],
  ['test_timestamps_normalised_to_utc_grid', 'UTC, canonical grid per utility, no duplicates', 'FR-06', 'Pass'],
  ['test_to_utc_handles_london_dst', '00:30 GMT and 02:30 BST on 29 March 2026 are one hour apart', 'FR-06', 'Pass'],
  ['test_hourly_common_axis', 'Hourly cross-utility frame', 'FR-21', 'Pass'],
  ['test_features_are_causal', 'Features for a reading do not change when later data are added', 'FR-07', 'Pass'],
  ['test_features_present', 'All features computed for scorable rows', 'FR-07', 'Pass'],
  ['test_uk_lcl_adapter', 'London smart-meter format parsed; half-hours split into 15-min readings; energy preserved', 'FR-02', 'Pass'],
  ['test_threshold_respects_alert_budget', 'Calibrated threshold flags ≤ 15% of readings', 'FR-12', 'Pass'],
  ['test_engine_scores_every_detector', 'Every detector and the ensemble produce scores and flags; ensemble in [0, 1]', 'FR-09–12', 'Pass'],
  ['test_threshold_override_is_applied', 'Operator threshold change takes effect and can be reverted', 'FR-18', 'Pass'],
  ['test_explainer_shap_and_lime', 'SHAP and LIME return one attribution per feature', 'FR-13, 14', 'Pass'],
  ['test_stream_processor_matches_record_path', 'Streaming micro-batches process > 1,000 records, remove duplicates, non-negative latency', 'FR-05', 'Pass'],
  ['test_alert_rules', 'Site mapping, severity, escalation after 30 min, debounce of events', 'FR-16', 'Pass'],
  ['test_narrative_is_direction_aware', 'Narrative says "below" for low and "above" for high readings', 'FR-15', 'Pass'],
  ['test_sus_scoring_reference_values', 'SUS gives 100, 0 and 50 for reference answer patterns', 'FR-27', 'Pass'],
  ['test_study_analysis_on_fabricated_fixture', 'Per-participant scores and H3 ratio computed correctly (fixture data only)', 'FR-27', 'Pass'],
  ['test_api_health_and_readings_demo', 'API health and readings endpoints; write endpoint refuses requests without key', 'FR-25', 'Pass'],
], [3.2, 4.0, 1.0, 0.8], { numeric: false }));
add(P(`Interface acceptance was tested by launching the dashboard and capturing every page at 1,440 px width with a scripted headless browser, recording any Python exception or browser error, then checking the interactive flows manually (replay controls, alert acknowledgement written to the audit trail, threshold change, study consent and task flow). Testing found defects that were fixed before the final runs; the significant ones are listed in ${tab('defects')} because several changed the experimental results.`));
add(table('defects', 'Significant defects found by testing and their effect', ['ID', 'Defect', 'Found by', 'Fix and effect'], [
  ['D1', 'LIME weights read from the wrong label of the regression explanation, flipping signs', 'Low SHAP–LIME agreement (Jaccard 0.03)', 'Read the correct label and discretise features; agreement rose to 0.59'],
  ['D2', 'Moving-average threshold maximised F1 by flagging 99% of readings', 'Implausible alert rate in evaluation', 'Alert budget of ≤ 15% in calibration; recall 0.99 → 0.28, precision 0.03 → 0.07'],
  ['D3', '8-step moving-average window had ROC-AUC below 0.5', 'Evaluation report', 'Standard 24-hour window; AUC 0.43 → 0.56'],
  ['D4', 'One record per scoring call limited throughput to ~10 readings/s', 'Performance test', 'Micro-batch scoring; ~180 readings/s'],
  ['D5', 'Too many single-reading alerts (846 candidate events, 11% precision)', 'Alert review', 'Debounce rule; 461 events, 18% precision, 88% coverage of true events'],
  ['D6', 'Dashboard crashes from a column-name clash and a deprecated chart argument', 'Scripted page rendering', 'Renamed column, updated API; all pages render without exceptions'],
], [0.5, 3.0, 2.3, 3.2], { numeric: false }));

add(H2('5.3 Streaming and Performance Testing'));
add(P(`The performance test measures the latency that H2 refers to: the time from a reading being published by the producer until it has been validated, cleaned, featurised, scored by all five detectors and the ensemble, explained if flagged, and committed to the database. ${tab('perf_setup')} describes the environment. Two runs were made. In the **steady** run the producer replayed one simulated test day (plus the 26-hour warm-up) at 1,800× real time, i.e. faster than any real network would report but below the consumer\'s capacity. In the **stress** run the same data were published as fast as possible, creating a backlog, to find the maximum sustainable throughput of one consumer.`));
add(table('perf_setup', 'Performance-test environment', ['Item', 'Value'], [
  ['Hardware', 'One virtual machine, 2 vCPU, 7.8 GB RAM (producer, broker, consumer and database co-located)'],
  ['Message broker', 'Apache Kafka 3.9.1, KRaft mode, single broker'],
  ['Database', 'PostgreSQL 16.4 (TimescaleDB extension not available in this environment)'],
  ['Consumer', 'One process; poll of up to 200 records; micro-batch scoring; TreeSHAP on alerts'],
  ['Measurement', 'produced_at stamped by producer; committed_at after database commit; per-reading log in reports/stream_latency.csv'],
], [2, 7], { numeric: false }));
add(P('An in-process benchmark was also run inside the evaluation script: 3,000 test-period records passed through the same `StreamProcessor` without Kafka in micro-batches of 50, measuring processing latency, throughput, CPU and memory with psutil. Comparing the two isolates the overhead of the broker and database.'));

add(H2('5.4 Anomaly Detection Evaluation'));
add(P(`The detectors were evaluated on the held-out test period (15 days, 32,387 scorable readings, 1,076 anomalous) with the metrics in ${tab('metrics_def')}. Two levels were used. **Point-level** metrics treat every reading as a classification and follow the proposal\'s framework. **Event-level** recall counts an anomaly episode as detected if any of its readings (or the two following) is flagged; this matters operationally because one timely alert per incident is what an operator needs.`));
add(table('metrics_def', 'Evaluation metrics', ['Metric', 'Definition', 'Why'], [
  ['Precision', 'Flagged readings that are truly anomalous', 'Cost of false alarms to operators'],
  ['Recall', 'Anomalous readings that are flagged', 'Missed incidents'],
  ['F1', 'Harmonic mean of precision and recall at the calibrated threshold', 'Single operating-point summary'],
  ['ROC-AUC', 'Area under the ROC curve over all thresholds', 'Threshold-free ranking quality'],
  ['Recall at 5% FPR', 'Recall when each detector\'s threshold is set to give 5% false positives', 'Fair comparison at equal alarm rate (used for H1)'],
  ['Event recall, detection delay', 'Share of episodes detected; median time from onset to first flag', 'Operational usefulness'],
  ['Scoring cost', 'Batch scoring time on the test period ÷ readings (best of 3)', 'Computational cost of each method'],
], [2.0, 4.3, 2.7], { numeric: false }));
add(P('H1 was tested on the temporal group (drift, leak and stuck) on two bases: at each detector\'s calibrated threshold, and at a matched 5% false-positive rate, which removes the effect of threshold choice. Because the data are synthetic and a single run could be favourable or unfavourable by chance, the complete pipeline — data generation, training, calibration and testing — was repeated with three random seeds (42, 7 and 123). Explanation quality was assessed by **plausibility**: for each correctly detected anomaly, whether the top SHAP feature is one of the features expected to drive that anomaly type (for example `flat_run` for a stuck meter), compared with the chance rate.'));

// ======================= 6 RESULTS =======================
add(H1('6. Results'));
add(H2('6.1 Platform Performance'));
add(P(`${tab('latency')} reports the latency measurements and ${fig('lat')} the distribution for the steady run. Across 3,968 readings the mean end-to-end latency was **0.69 s**, the 95th percentile 1.28 s and the maximum 1.56 s; **100% of readings** were committed within the 2.5-second target, and alerts specifically were available after 0.54 s on average. **H2 is therefore supported** in the test environment.`));
add(table('latency', 'End-to-end and processing latency (measured)', ['Measurement', 'n', 'Mean', 'p50', 'p95', 'p99', 'Max'], [
  ['Steady run, producer → database commit (all readings)', '3,968', '0.69 s', '0.74 s', '1.28 s', '1.36 s', '1.56 s'],
  ['Steady run, alerts only', '205', '0.54 s', '—', '1.14 s', '—', '—'],
  ['In-process only (no Kafka/database), micro-batch 50', '2,833', '0.61 s', '0.62 s', '0.78 s', '0.83 s', '0.83 s'],
  ['Stress run (backlog), producer → commit', '4,014', '11.5 s', '—', '20.6 s', '—', '21.5 s'],
], [3.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]));
add(image(FIG('fig8_latency.png'), 600, 'Distribution of end-to-end latency in the steady run (left) and cumulative distributions for the steady and stress runs (right, log scale). Dashed red line: H2 target of 2.5 s.', 'lat'));
add(P('The plain-language narrative was added to the streaming alert path after these measurements. It was timed separately at about 4 µs per alert, so it does not change the results. Two further observations qualify the result. First, the in-process latency (0.61 s) is close to the end-to-end figure (0.69 s), so most of the time is spent waiting for and scoring a micro-batch rather than in Kafka or the database; latency could be reduced further with smaller polls at the cost of throughput. Second, the stress run shows the limit: with a backlog, one consumer sustained about **180 readings per second**, and latency then reflects queueing (mean 11.5 s). At 15-minute reporting, 180 readings per second corresponds to roughly 160,000 meters per consumer process; because messages are keyed by meter, capacity can be increased by adding Kafka partitions and consumers, although this scale-out was not benchmarked. During the in-process benchmark the consumer used about 52% of the two CPUs and 820 MB of memory. Whole-engine batch scoring on the test period ran at about 48,000 readings per second, confirming that model inference is not the bottleneck.'));

add(H2('6.2 Anomaly Detection Results'));
add(P(`${tab('main')} gives the main detection results on the test period for seed 42, and ${fig('f1auc')} compares F1 and ROC-AUC. The table follows the format planned in the proposal, with detection latency reported as two measured quantities: the median delay from anomaly onset to the first flag, and the marginal scoring cost per reading.`));
add(table('main', 'Detection results on the held-out test period (seed 42; 32,387 readings, 1,076 anomalous, 149 episodes)', ['Model', 'Precision', 'Recall', 'F1', 'ROC-AUC', 'Event recall', 'Median delay (E / G / W, min)', 'Scoring cost (µs/reading)'], [
  ['Z-score', '0.317', '0.769', '0.449', '0.926', '0.832', '0 / 0 / 0', '< 0.01*'],
  ['Moving average (24 h)', '0.070', '0.276', '0.112', '0.564', '0.389', '0 / 0 / 0', '< 0.01*'],
  ['STL (offline)', '0.175', '0.416', '0.246', '0.780', '0.732', '15 / 90 / 0', '400 (batch, needs future data)'],
  ['Isolation Forest', '0.412', '0.574', '0.480', '0.933', '0.517', '0 / 0 / 0', '8.5'],
  ['One-Class SVM', '0.480', '0.599', '0.533', '0.877', '0.604', '0 / 30 / 0', '5.0'],
  ['LSTM autoencoder', '0.590', '0.571', '**0.580**', '0.916', '0.396', '15 / 60 / 0', '6.3'],
  ['Ensemble', '0.395', '0.755', '0.519', '**0.946**', '**0.886**', '0 / 0 / 0', '≈ 20 (sum of members)'],
], [1.75, 1.15, 0.9, 0.8, 1.0, 1.0, 1.5, 1.7], { highlight: (r) => r === 6 }));
add(P('* The statistical detectors read a feature (`profile_z`, `ma_z`) that the ingestion layer has already computed, so their marginal cost is negligible; the shared feature-extraction cost is included in the end-to-end latency of Section 6.1. STL cost is the full offline decomposition of all 30 meters (52 s) divided by readings.'));
add(image(FIG('fig4_f1_auc.png'), 600, 'F1 at the calibrated threshold and threshold-free ROC-AUC for each technique (test period, seed 42).', 'f1auc'));
add(P(`As shown in ${tab('main')}, the LSTM autoencoder achieved the highest point-level F1 (0.580), driven by the highest precision of any method (0.590), followed by the ensemble (0.519) and the One-Class SVM (0.533). The ensemble, however, ranked readings best overall, with the highest ROC-AUC (0.946), and detected the largest share of anomaly episodes (88.6%, against 83.2% for the Z-score and only 39.6% for the LSTM). The two views are not contradictory: the LSTM is precise on the readings it flags but misses whole episodes, mainly short water events, whereas the ensemble catches almost every episode at the price of more false alarms. For an operator, who needs one timely alert per incident, the event-level view is arguably more relevant.`));
add(P(`The ROC curves in ${fig('roc')} make the threshold-free comparison visible. Z-score, Isolation Forest, LSTM and ensemble form a close group with AUC between 0.916 and 0.946, and the ensemble curve lies on or above the others over most of the range. The STL comparator (AUC 0.780) and the moving average (0.564) are clearly weaker. STL performed worse than the profile Z-score despite seeing future data: the robust decomposition absorbs sustained anomalies such as drift and leaks into its trend component, so their residuals are small — recall on drift was 0.38 for STL against 0.84 for Z-score (${tab('main')} and ${fig('types')}). The moving average fails for a related reason: sustained anomalies drag its 24-hour baseline with them.`));
add(image(FIG('fig6_roc.png'), 430, 'ROC curves on the test period. The dashed vertical line marks the 5% false-positive rate used for the matched comparison in H1.', 'roc'));
add(P('Detection delay was short for all streaming methods: the median detected episode was flagged at its first anomalous reading, except the LSTM, which needed 15 minutes for electricity and 60 minutes for gas because an anomaly must fill part of its 16-step window before the reconstruction error rises. STL showed the longest delays on gas (90 minutes).'));

add(H2('6.3 Comparison of Detection Methods'));
add(H3('6.3.1 Across utility types'));
add(P(`${tab('utilf1')} and ${fig('util')} break F1 down by utility, which is the comparison across utility types promised as Outcome 2. All methods performed best on electricity and worst on water. The LSTM was best on electricity (0.683), Z-score on gas (0.539) and the ensemble on water (0.368). Water is hardest because its irregular readings are re-gridded and partly interpolated (Section 4.2.2), which smooths short events, and because water draws are intermittent, so a normal reading can be far from the hourly profile.`));
add(table('utilf1', 'F1 by utility on the test period (seed 42); best per utility in bold', ['Model', 'Electricity', 'Gas', 'Water'], [
  ['Z-score', '0.530', '**0.539**', '0.293'],
  ['Moving average (24 h)', '0.170', '0.075', '0.047'],
  ['STL (offline)', '0.416', '0.290', '0.136'],
  ['Isolation Forest', '0.636', '0.425', '0.189'],
  ['One-Class SVM', '0.628', '0.491', '0.320'],
  ['LSTM autoencoder', '**0.683**', '0.511', '0.270'],
  ['Ensemble', '0.639', '0.432', '**0.368**'],
], [3, 2, 2, 2]));
add(image(FIG('fig7_f1_by_utility.png'), 600, 'F1 by technique and utility (test period, seed 42).', 'util'));
add(H3('6.3.2 Across anomaly types'));
add(P(`${fig('types')} shows recall by anomaly type. Spikes were detected by almost every method. The other types separate the methods: Z-score was strongest on drift (0.84) and good on leaks (0.68); Isolation Forest and One-Class SVM were strongest on stuck meters (0.88 and 0.87), because the ⟦flat_run⟧ feature makes a constant value easy to isolate; and the ensemble combined these strengths, giving the most even profile (0.70–1.00 on every type, and the best leak recall at 0.72). This complementarity is the main justification for the ensemble.`));
add(image(FIG('fig5_recall_by_type.png'), 470, 'Recall by anomaly type and technique (test period, seed 42).', 'types'));
add(H3('6.3.3 Hypothesis H1'));
add(P(`H1 predicted that the LSTM autoencoder would achieve at least 15% higher recall on temporal anomalies than the statistical methods and Isolation Forest. ${tab('h1')} and ${fig('h1')} report the test across three seeds.`));
add(table('h1', 'H1: relative recall of the LSTM autoencoder on temporal anomalies (drift, leak, stuck)', ['Seed', 'Basis', 'LSTM recall', 'vs Z-score', 'vs Moving avg', 'vs Isolation Forest', 'H1 (≥ +15% vs all)'], [
  ['42', 'Calibrated threshold', '0.555', '−26.6%', '+148.4%', '+3.3%', 'Not supported'],
  ['42', 'Matched 5% FPR', '0.561', '−22.6%', '+372.0%', '−11.3%', 'Not supported'],
  ['7', 'Calibrated threshold', '0.703', '+3.6%', '+355.5%', '+26.6%', 'Not supported'],
  ['7', 'Matched 5% FPR', '0.607', '−7.3%', '+631.2%', '−9.1%', 'Not supported'],
  ['123', 'Calibrated threshold', '0.603', '+9.6%', '+303.8%', '+35.2%', 'Not supported'],
  ['123', 'Matched 5% FPR', '0.429', '−34.8%', '+336.5%', '−31.6%', 'Not supported'],
], [0.7, 1.8, 1.1, 1.1, 1.3, 1.5, 1.6]));
add(image(FIG('fig9_h1_seeds.png'), 560, 'Recall on temporal anomalies at the calibrated threshold for the LSTM and the H1 comparison methods, for each seed.', 'h1'));
add(P('**H1 is not supported.** The LSTM exceeded the moving average by a wide margin in every case (+148% to +631%) and exceeded Isolation Forest at the calibrated threshold in two of three seeds (+26.6% and +35.2%), but it never reached the required +15% over the Z-score, and at a matched false-positive rate it was below both Z-score and Isolation Forest in every seed. The most likely explanation is in the design of the Z-score detector: by comparing each reading with the meter\'s own median for that hour and day type, it already encodes the temporal context that the LSTM must learn from a 16-step window, and for sustained shifts a per-reading comparison with a stable baseline is a strong signal. The LSTM may benefit from longer windows or real data with richer temporal structure, but the configuration was selected on validation data and was not tuned further on the test period to rescue the hypothesis. This negative result is itself a contribution: on seasonal consumption data, a well-designed profile baseline is a demanding benchmark that deep models must be shown to beat.'));
add(H3('6.3.4 Robustness across seeds'));
add(P(`${tab('robust')} reports the mean and standard deviation over the three seeds. The ranking by ROC-AUC is stable — the ensemble is first in all three seeds with the smallest spread (0.940 ± 0.008) — whereas the LSTM\'s F1 varies most (0.432 ± 0.129). The single-seed result that the LSTM has the highest F1 does not therefore generalise; averaged over seeds, the One-Class SVM (0.486) and the ensemble (0.477) have the highest F1.`));
add(table('robust', 'Mean ± standard deviation over three seeds (42, 7, 123)', ['Model', 'F1', 'ROC-AUC', 'Temporal recall'], [
  ['Z-score', '0.433 ± 0.056', '0.912 ± 0.015', '0.661 ± 0.104'],
  ['Moving average (24 h)', '0.097 ± 0.013', '0.554 ± 0.015', '0.176 ± 0.041'],
  ['Isolation Forest', '0.439 ± 0.051', '0.923 ± 0.009', '0.513 ± 0.058'],
  ['One-Class SVM', '**0.486 ± 0.042**', '0.896 ± 0.018', '0.603 ± 0.112'],
  ['LSTM autoencoder', '0.432 ± 0.129', '0.896 ± 0.022', '0.620 ± 0.076'],
  ['Ensemble', '0.477 ± 0.045', '**0.940 ± 0.008**', '**0.671 ± 0.042**'],
], [3, 2, 2, 2]));
add(H3('6.3.5 Accuracy, latency and interpretability (RQ2)'));
add(P(`RQ2 asks for the best balance of accuracy, latency and interpretability. ${fig('cost')} plots F1 against marginal scoring cost. The statistical Z-score is effectively free and fully interpretable and reaches an F1 of 0.449 with the highest recall; the machine-learning and deep-learning detectors cost between 5 and 9 µs per reading — three orders of magnitude more than the statistical methods, yet still negligible against the 2.5-second budget — for a modest gain in F1. Since every streaming method, including the full ensemble with SHAP, stayed well inside the latency target, latency does not discriminate between them on this hardware; accuracy and interpretability do.`));
add(image(FIG('fig10_cost_vs_f1.png'), 440, 'Detection accuracy (F1) against marginal scoring cost per reading (log scale).', 'cost'));
add(P(`Interpretability was assessed through the explanation results in ${tab('xai')}. For correctly detected anomalies, the top TreeSHAP feature was one of the expected drivers of that anomaly type in 78.6% of cases, against a chance rate of about 24%, and one of the top three in 98.0%. TreeSHAP cost 3.2 ms per alert, small enough to run on every alert in the stream, while LIME (36 ms) and KernelSHAP (111 ms) are suited to on-demand use. KernelSHAP and LIME on the same ensemble agreed on 59% of top-three features (Jaccard), and TreeSHAP on the Isolation Forest agreed with LIME on the ensemble on 49%, which shows that different explainers emphasise different features and supports showing a plain-language narrative rather than raw attributions to operators.`));
add(table('xai', 'Explainability results (test period, seed 42)', ['Measure', 'Result'], [
  ['Alerts explained with TreeSHAP in the stream', '2,056 at 3.2 ms per alert'],
  ['Top-1 SHAP feature is an expected driver (true positives)', '78.6% (chance ≈ 24%)'],
  ['Top-3 contains an expected driver', '98.0%'],
  ['Top-3 agreement, KernelSHAP vs LIME, same ensemble (Jaccard)', '0.59'],
  ['Top-3 agreement, TreeSHAP (Isolation Forest) vs LIME (ensemble)', '0.49'],
  ['Cost: LIME / KernelSHAP per alert (sample of 60)', '36 ms / 111 ms'],
], [6, 3], { numeric: false }));
add(P('Taking the three criteria together, the answer to RQ2 is that **the weighted ensemble offers the best balance for multi-utility monitoring**: it has the highest and most stable ROC-AUC, the highest event recall and the most even performance across anomaly types and utilities, it stays far inside the latency budget, and its decisions can be explained per alert with TreeSHAP and on demand with LIME. Where a single, fully transparent method is required, the profile Z-score is the strongest choice; the LSTM autoencoder did not justify its additional complexity on this data.'));

add(H2('6.4 Dashboard Results'));
add(P(`All eight dashboard pages were implemented and rendered without errors in acceptance testing (Section 5.2), and every functional requirement for the visualisation layer was met (FR-19 to FR-24 in the requirements specification). ${tab('alerts')} shows the effect of the alert-management rules on what the operator sees during the 15-day test period.`));
add(table('alerts', 'Alert management outcomes on the test period (measured)', ['Measure', 'Before debounce', 'After debounce'], [
  ['Alert events', '846', '461'],
  ['Event precision (event overlaps a true anomaly)', '11.1%', '17.6%'],
  ['True anomaly episodes covered by at least one alert', '—', '88%'],
  ['Severity: critical / warning / info', '—', '195 / 255 / 11'],
  ['Events linked as cross-utility (same site, within 2 h)', '—', '242'],
], [5, 2, 2]));
add(P('The debounce rule nearly halved the alert volume and raised event precision from 11% to 18% while still covering 88% of genuine episodes. Alert-level precision nevertheless remains the platform\'s weakest operational figure: most false alerts are single electricity readings at evening peaks, where normal variation is largest. This is precisely where the operator-adjustable thresholds and the explanations are expected to help, and it is the question the user study is designed to answer.'));
add(P('**H3 and usability (SUS, TAM) are not yet measured.** The study instrument is complete and tested: participants give consent, are randomly assigned to the explained (XAI) or black-box condition, review the same eight alerts (five genuine, three false alarms), and complete the trust, SUS and TAM questionnaires; the analysis script computes SUS, trust and TAM scores, decision accuracy, a Mann–Whitney U test and the H3 ratio. The analysis has been verified only on fixture data, and no trust or usability figures are reported here because none have yet been collected from real participants. Results will be reported in the final thesis once ethical approval has been confirmed and the study has been run.'));

add(H2('6.5 Summary of Findings'));
add(table('summary', 'Summary against research questions and hypotheses', ['Question', 'Finding', 'Evidence'], [
  ['RQ1: scalable real-time architecture', 'A Kappa architecture with Kafka, a shared stream processor and time-series storage integrated three utilities at different frequencies through one code path', 'Sections 4.1–4.4; ' + tab('ingest') + ', ' + tab('latency')],
  ['RQ2: best balance', 'Weighted ensemble: highest ROC-AUC (0.946; 0.940 ± 0.008 over seeds) and event recall (88.6%), within latency budget, explainable per alert', 'Tables ' + tabIds.main + '–' + tabIds.xai + '; Figures ' + figIds.f1auc + '–' + figIds.cost],
  ['RQ3: dashboard effectiveness', 'Dashboard complete; alerts debounced and explained; plausible explanations (78.6% top-1); operator study pending', 'Section 6.4; ' + tab('xai') + ', ' + tab('alerts')],
  ['H1: LSTM ≥ 15% higher temporal recall', 'Not supported: below Z-score at matched FPR in all seeds', tab('h1') + '; ' + fig('h1')],
  ['H2: mean alert latency < 2.5 s', 'Supported: 0.69 s mean, 1.56 s max, 100% under target', tab('latency') + '; ' + fig('lat')],
  ['H3: XAI raises trust ≥ 20%', 'Not yet tested (requires participants)', 'Section 6.4'],
], [2.4, 4.6, 2.0], { numeric: false }));
add(P(`${tab('outcomes')} relates the results to the expected outcomes and contributions stated in Section 4 of the proposal.`));
add(table('outcomes', 'Expected outcomes of the proposal and what was delivered', ['Outcome', 'Delivered', 'Evidence'], [
  ['O1: validated five-layer architecture with documented performance', 'Delivered: implemented, tested (18 automated tests) and measured (latency, throughput, resources)', 'Ch. 4; Sections 5.2, 6.1'],
  ['O2: empirical comparison of detection techniques across utility types', 'Delivered: six streaming methods and STL compared overall, per utility, per anomaly type, over three seeds', 'Sections 6.2–6.3'],
  ['O3: evidence of XAI impact on trust and decision quality', 'Partly delivered: explanation plausibility and cost measured; trust effect pending the user study', 'Sections 6.3.5, 6.4'],
  ['O4: deployment recommendations for UK multi-utility providers', 'Delivered: recommendations below, and deployment guide in the repository', 'Table ' + tabIds.deploy],
], [3, 4, 2], { numeric: false }));
add(P(`**Deployment recommendations (Outcome 4).** ${tab('deploy')} summarises the recommendations that follow from the results. The full guide, including container deployment and a zero-infrastructure dashboard option, is in `+'`docs/DEPLOYMENT.md`'+`.`));
add(table('deploy', 'Deployment recommendations for a UK multi-utility operator', ['Area', 'Recommendation', 'Basis in results'], [
  ['Architecture', 'Keep the Kappa design; scale by adding Kafka partitions and consumers keyed by meter', 'One consumer ≈ 180 readings/s (≈ 160,000 meters at 15-min reporting); Section 6.1'],
  ['Detection', 'Deploy the weighted ensemble; keep the profile Z-score as the transparent fallback', 'Highest and most stable ROC-AUC and event recall; Sections 6.2–6.3'],
  ['Explainability', 'TreeSHAP and narrative on every alert; LIME only on demand', '3.2 ms vs 36 ms per alert; Table ' + tabIds.xai],
  ['Human oversight', 'Monitoring-only operation; operator-approved thresholds; audit every action', 'Ethics commitment; false-alarm rate in Table ' + tabIds.alerts],
  ['Avoid', 'Serverless functions in the alert path', 'Cold-start latency risks the 2.5 s target (H2)'],
  ['Regulation and data', 'Treat as part of an essential service under the NIS Regulations 2018 and the NCSC Cyber Assessment Framework; pseudonymise meter IDs; host in a UK region', 'Data protection and resilience duties of energy and water operators'],
  ['Before roll-out', 'Re-run the evaluation on the operator\'s own labelled incidents, then pilot in shadow mode', 'Synthetic results rank methods but do not predict field precision; Section 6.5'],
], [1.6, 4.2, 3.2], { numeric: false }));
add(P('**Interpretation.** The platform demonstrates that heterogeneous electricity, gas and water streams can be processed in near-real time on very modest hardware: the latency target was met with a large margin, and inference cost was not the constraint — feature design and alert management were. The comparison shows that no single detector dominates: the profile Z-score is hard to beat on sustained deviations, tree- and kernel-based models are strongest on stuck meters, and the LSTM is precise but misses short events. Combining them gave the most reliable ranking and the most even coverage, which is the main practical recommendation for a UK multi-utility operator.'));
add(P('**Threats to validity.** (1) The data are synthetic, and anomaly shapes and noise were designed, so absolute scores will not transfer to field data; the ranking of methods is the more transferable result, and the SGCC and London adapters allow it to be re-tested on real data. (2) The study used 30 meters; per-utility results for gas and water rest on a few hundred anomalous readings and 14 and 118 episodes respectively. (3) Latency was measured on a single broker with co-located services and without the TimescaleDB extension; network hops in a real deployment would add time, although the margin to the target is large. (4) The LSTM explanation gap remains: per-reading SHAP and LIME do not cover the window-based model. (5) H3 is untested until the user study is completed.'));

// ---- references
add(H1('References'));
const refs = [
  'Brooke, J. (1996) \'SUS: a "quick and dirty" usability scale\', in Jordan, P.W., Thomas, B., Weerdmeester, B.A. and McClelland, I.L. (eds) Usability Evaluation in Industry. London: Taylor & Francis, pp. 189–194.',
  'Cleveland, R.B., Cleveland, W.S., McRae, J.E. and Terpenning, I. (1990) \'STL: a seasonal-trend decomposition procedure based on loess\', Journal of Official Statistics, 6(1), pp. 3–73.',
  'Davis, F.D. (1989) \'Perceived usefulness, perceived ease of use, and user acceptance of information technology\', MIS Quarterly, 13(3), pp. 319–340. doi: 10.2307/249008.',
  'Hevner, A.R., March, S.T., Park, J. and Ram, S. (2004) \'Design science in information systems research\', MIS Quarterly, 28(1), pp. 75–105. doi: 10.2307/25148625.',
  'Jian, J.-Y., Bisantz, A.M. and Drury, C.G. (2000) \'Foundations for an empirically determined scale of trust in automated systems\', International Journal of Cognitive Ergonomics, 4(1), pp. 53–71.',
  'Kreps, J. (2014) Questioning the Lambda Architecture. O\'Reilly Radar, 2 July. Available at: https://www.oreilly.com/radar/questioning-the-lambda-architecture/.',
  'Liu, F.T., Ting, K.M. and Zhou, Z.-H. (2008) \'Isolation forest\', in Proceedings of the 8th IEEE International Conference on Data Mining. Pisa: IEEE, pp. 413–422. doi: 10.1109/ICDM.2008.17.',
  'Lundberg, S.M. and Lee, S.-I. (2017) \'A unified approach to interpreting model predictions\', in Advances in Neural Information Processing Systems 30, pp. 4765–4774.',
  'Lundberg, S.M., Erion, G., Chen, H., DeGrave, A., Prutkin, J.M., Nair, B., Katz, R., Himmelfarb, J., Bansal, N. and Lee, S.-I. (2020) \'From local explanations to global understanding with explainable AI for trees\', Nature Machine Intelligence, 2(1), pp. 56–67. doi: 10.1038/s42256-019-0138-9.',
  'Malhotra, P., Ramakrishnan, A., Anand, G., Vig, L., Agarwal, P. and Shroff, G. (2016) \'LSTM-based encoder-decoder for multi-sensor anomaly detection\', ICML 2016 Anomaly Detection Workshop. arXiv: 1607.00148.',
  'Peffers, K., Tuunanen, T., Rothenberger, M.A. and Chatterjee, S. (2007) \'A design science research methodology for information systems research\', Journal of Management Information Systems, 24(3), pp. 45–77. doi: 10.2753/MIS0742-1222240302.',
  'Ribeiro, M.T., Singh, S. and Guestrin, C. (2016) \'"Why should I trust you?": explaining the predictions of any classifier\', in Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, pp. 1135–1144. doi: 10.1145/2939672.2939778.',
  'Schölkopf, B., Platt, J.C., Shawe-Taylor, J., Smola, A.J. and Williamson, R.C. (2001) \'Estimating the support of a high-dimensional distribution\', Neural Computation, 13(7), pp. 1443–1471. doi: 10.1162/089976601750264965.',
  'UK Power Networks (2014) SmartMeter Energy Consumption Data in London Households. London Datastore. Available at: https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households.',
  'Zheng, Z., Yang, Y., Niu, X., Dai, H.-N. and Zhou, Y. (2018) \'Wide and deep convolutional neural networks for electricity-theft detection to secure smart grids\', IEEE Transactions on Industrial Informatics, 14(4), pp. 1606–1615. doi: 10.1109/TII.2017.2785963.',
];
refs.forEach((r) => add(new Paragraph({ children: runs(r, { size: 20 }), spacing: { after: 120, line: 280 }, indent: { left: 432, hanging: 432 } })));

add(H1('Appendix A: Reproducing the Results'));
add(P('All results can be regenerated from the repository on a machine with Python 3.12 or later:'));
['`pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt`',
  '`PYTHONPATH=src python -m confluence.evaluation.run` — data, training, calibration, test metrics, H1, in-process latency, explainability (reports/metrics.json, reports/evaluation_report.md)',
  '`PYTHONPATH=src python -m confluence.evaluation.run --seed 7` and `--seed 123` — robustness runs (reports/seeds/)',
  '`PYTHONPATH=src python scripts/supplementary_experiments.py` — STL comparator, scoring cost, detection delay (reports/supplementary.json)',
  '`docker compose up --build`, then `python -m confluence.evaluation.stream_latency` — Kafka latency (reports/stream_kafka_latency.json)',
  '`python scripts/make_figures.py` — Figures 2 and 8–14',
  '`python -m pytest` — the 18 functional tests',
].forEach((t) => add(B(t)));

add(H1('Appendix B: Key Code Excerpts'));
add(P('The excerpts below are copied unchanged from the repository, to show how the central design decisions of Section 4.5 are implemented.'));
const CODE = (title, file, src) => {
  add(new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true, children: [new TextRun({ text: title + ' — ', bold: true, size: 20 }), new TextRun({ text: file, font: 'Consolas', size: 18 })] }));
  src.replace(/\s+$/, '').split('\n').forEach((line, i, arr) => add(new Paragraph({
    shading: { fill: 'F3F3F1', type: ShadingType.CLEAR }, spacing: { after: 0, line: 240 }, keepLines: true, keepNext: i < arr.length - 1,
    children: [new TextRun({ text: line.replace(/ /g, '\u00A0') || ' ', font: 'Consolas', size: 15 })] })));
  add(new Paragraph({ spacing: { after: 160 }, children: [] }));
};
CODE('B.1 Threshold calibration with alert budget (Section 4.5.4)', 'src/confluence/detection/base.py', "def calibrate_threshold(scores: np.ndarray, y: np.ndarray | None, mode: str = \"f1\",\n                        contamination: float = 0.03, max_alert_rate: float = 0.15) -> float:\n    \"\"\"Pick an alert threshold on the validation period.\n\n    ``f1``       maximise F1 against validation labels (semi-supervised calibration)\n    ``quantile`` flag the top ``contamination`` share of readings (fully unsupervised)\n\n    In both modes the threshold never flags more than ``max_alert_rate`` of\n    readings \u2014 an operational alert budget that stops a weak detector from\n    \"winning\" F1 by alerting on almost everything.\n    \"\"\"\n    ok = ~np.isnan(scores)\n    s = scores[ok]\n    floor = float(np.quantile(s, 1 - max_alert_rate))\n    if mode == \"quantile\" or y is None:\n        return max(float(np.quantile(s, 1 - contamination)), floor)\n    p, r, t = precision_recall_curve(y[ok].astype(int), s)\n    if not len(t):\n        return max(float(np.quantile(s, 0.97)), floor)\n    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)\n    f1[t < floor] = -1\n");
CODE('B.2 Weighted-voting ensemble (Section 4.5.4)', 'src/confluence/detection/engine.py', "    def _ensemble_score(um: UtilityModels, df: pd.DataFrame, raw: dict | None = None) -> np.ndarray:\n        acc = np.zeros(len(df)); wsum = np.zeros(len(df))\n        for name, det in um.detectors.items():\n            s = raw[name] if raw is not None else det.score(df)\n            p = um._pct(name, s)\n            ok = ~np.isnan(p)\n            acc[ok] += um.weights[name] * p[ok]; wsum[ok] += um.weights[name]\n        out = np.where(wsum > 0, acc / np.maximum(wsum, 1e-12), np.nan)\n        return np.where(df[\"scorable\"].values, out, np.nan)\n");
CODE('B.3 Explanation of each streamed alert (Sections 4.3, 4.5.5)', 'src/confluence/ingestion/stream_processor.py', "            alert = bool(row[\"flag_ensemble\"])\n            shap_top, narr = [], \"\"\n            if alert and self.explainer is not None:\n                x = row[FEATURES].astype(float).fillna(0).values[None, :]\n                shap_top = self.explainer.top(self.explainer.shap_values(utility, x)[0])\n                narr = narrative(utility, n[\"meter_id\"], float(n[\"value\"]), UTILITIES[utility].unit, shap_top,\n                                 dict(zip(FEATURES, x[0])))\n");

// ======================= DOCUMENT =======================
const doc = new Document({
  creator: 'Confluence project', title: 'Implementation, Testing and Results',
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 32, bold: true, color: '000000' }, paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 26, bold: true, color: '000000' }, paragraph: { spacing: { before: 300, after: 140 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 23, bold: true, color: '1B474D' }, paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '595959' })] })] }) },
    children: C,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync('/home/user/workspace/dissertation/7CS077-Implementation-Testing-Results.docx', b); console.log('written'); });
