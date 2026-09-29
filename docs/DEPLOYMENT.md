# Deployment guide and UK recommendations (Outcome 4)

## 1. Dashboard only (zero infrastructure) — Streamlit Community Cloud

The dashboard runs in **demo mode** from the committed artifacts (`artifacts/`, `reports/`) with no Kafka or database.

1. Sign in at share.streamlit.io with the GitHub account that owns this repository.
2. Click **Create app** and choose this repository, branch `main`, main file `dashboard/app.py`.
3. Under **Advanced settings**, choose Python 3.12. Dependencies come from `dashboard/requirements.txt` (no PyTorch).
4. Deploy. To use the hosted app for the user study, download responses regularly: Community Cloud storage is not persistent, and resources are shared and limited ([Streamlit docs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)). Alternatively, set `DATABASE_URL` as a secret so responses go to PostgreSQL.

Locally: `pip install -r dashboard/requirements.txt && streamlit run dashboard/app.py`

## 2. Full pipeline — Docker Compose

```bash
cp .env.example .env        # change every password and the API key
docker compose up --build   # timescaledb, kafka, trainer, consumer, producer, api, dashboard, backup
```

- Dashboard: http://localhost:8501 (switches to live database mode automatically)
- API: http://localhost:8000/docs
- The trainer runs `python -m confluence.evaluation.run` once, writes artifacts and creates the schema.
- The producer replays the test period at `REPLAY_SPEED` (600× by default) in a loop.
- `backup` writes a daily `pg_dump -Fc` to the `backups` volume and keeps `BACKUP_KEEP` dumps. Restore with `pg_restore --clean`.
- To reproduce the H2 measurement, run `python -m confluence.evaluation.stream_latency --since <unix time when the producer started>`.

## 3. Without Docker (how the integration run in this repo was done)

1. Start Kafka 3.9 in KRaft mode (`bin/kafka-storage.sh format …` then `bin/kafka-server-start.sh config/kraft/server.properties`) and PostgreSQL 16 (TimescaleDB is optional; the schema falls back to plain tables).
2. `export PYTHONPATH=src DATABASE_URL=postgresql://…`
3. `python -m confluence.evaluation.run`, then `python -c "from confluence.storage import db; db.init_schema()"`
4. `python -m confluence.ingestion.consumer` (in one shell), then `python -m confluence.ingestion.producer --speed 1800 --replay-days 1`

## 4. Recommendations for UK multi-utility providers

| Area | Recommendation | Why |
|---|---|---|
| Regulation | Treat the platform as part of an essential service. Energy and water operators designated as Operators of Essential Services fall under the NIS Regulations 2018 ([Ofgem guidance](https://www.ofgem.gov.uk/guidance/nis-directive-and-nis-regulations-2018-ofgem-guidance-operators-essential-services)) and are assessed against the NCSC Cyber Assessment Framework ([NCSC CAF](https://www.ncsc.gov.uk/sites/default/files/documents/NCSC_CAF_2.pdf)). | Monitoring systems handling network data are in scope for risk management and incident reporting. |
| Data protection | Smart-meter consumption at household level can be personal data under UK GDPR. Pseudonymise meter IDs at ingestion, keep a data-protection impact assessment, and apply the retention policy in `schema.sql` (400 days of raw data by default). | Data minimisation, and matches the proposal's ethics section. |
| Hosting region | Keep data in the UK. For example: AWS London (eu-west-2), which Timescale Cloud supports ([Timescale regions](https://github.com/timescale/docs/blob/latest/use-timescale/regions.md)), with Amazon MSK Serverless for Kafka, which is available in Europe (London) ([AWS](https://aws.amazon.com/about-aws/whats-new/2023/08/amazon-msk-serverless-additional-aws-regions/)). Azure UK South with Event Hubs (Kafka API) is an equivalent option. | Data residency, and low latency to UK head-end systems. |
| Architecture | Keep Kappa. Scale by adding Kafka partitions and consumers (one consumer handled about 180 readings/s on 2 vCPUs, roughly 160k meters at 15-minute reporting). Partition by meter ID so each meter's buffer stays on one consumer. | Measured headroom, with a simple, stateful per-meter design. |
| Avoid | Serverless functions in the alert path. | Cold-start latency risks the 2.5 s target. |
| Human oversight | Keep monitoring-only mode, operator-approved thresholds, and the audit log. Review threshold changes monthly. | Ethics requirement, and accountability for any decision taken from an alert. |
| Model operations | Retrain monthly or after tariff or season changes. Monitor alert precision from operator dismissals (the audit log is a free label source). Re-run `evaluation/run.py` before promoting a model. | Consumption profiles drift with season and occupancy. |
| Explainability | Show the narrative and SHAP factors on every alert. Use LIME only on demand (about 35 ms), since TreeSHAP costs about 3 ms. | The latency budget stays intact. |
| Security | Put the API behind TLS and SSO. Rotate `API_KEY` and DB passwords from a secrets manager. Use separate `confluence_ingest` and `confluence_readonly` roles. | CAF principles B2 (identity and access control) and B3 (data security). |
| Resilience | Nightly `pg_dump`, plus provider point-in-time recovery. Kafka replication factor 3 in production (1 in the demo). | Backup and recovery requirement from Figure 1. |
| Validation before roll-out | Re-run the evaluation on the provider's own historical data with labelled incidents, then run a shadow-mode pilot alongside existing alarms. | The synthetic results rank methods but do not predict field precision. |
