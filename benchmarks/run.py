"""Reproducible, synthetic retrieval benchmark. No LLM quality metrics asserted."""
import json, os, platform, statistics, sys, tempfile, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core import Store, embed_local

# Synthetic knowledge-base entries: intentionally varied, with distractors.
DATA=[
 ('Backups','Database backup files are retained for 90 days. The restoration verification team performs monthly integrity checks.','How many days do we keep database backups?'),
 ('Recovery','Disaster recovery RTO is 4 hours for tier one services. The recovery point objective is 60 minutes.','What is the tier one recovery time objective?'),
 ('Access','Privileged access reviews occur every 30 days. Administrators must use phishing resistant MFA.','How often are privileged permissions reviewed?'),
 ('Onboarding','New employee equipment is issued after identity verification and manager approval.','What must happen before providing new hire equipment?'),
 ('Expenses','Travel expense reports must be submitted within 15 calendar days of returning.','When is the travel reimbursement form due?'),
 ('Security','High severity cybersecurity incidents require notification of the response lead within 20 minutes.','How quickly should urgent security incidents be escalated?'),
 ('Retention','Customer support ticket history is kept for 18 months. A deletion job runs each quarter.','How long is support ticket history kept?'),
 ('Procurement','Software purchase requests above 25000 dollars require procurement director signoff.','Who approves large software purchasing requests?'),
 ('Encryption','Data at rest is encrypted with AES 256 encryption. Connections require TLS 1.3.','Which encryption standard protects stored records?'),
 ('Change','Production releases require one peer approval and successful automated checks.','What approvals do production deployments require?'),
 ('Training','Annual security awareness training is mandatory for all regular employees.','Is security awareness training required each year?'),
 ('Classification','Confidential documents must be labeled confidential and shared only through approved channels.','What label is required for sensitive confidential documents?'),
 ('Vendor','Third party vendors handling customer data require risk assessment before onboarding.','What should happen before adding a data handling supplier?'),
 ('Availability','The target monthly service uptime is 99.95 percent excluding planned outages.','What availability percentage does our service target?'),
 ('Passwords','Service account secrets rotate every 45 days via the centralized vault.','How frequently are service secrets rotated?'),
 ('Tickets','Priority two helpdesk tickets have a response target of 2 business hours.','What is the response SLA for priority two tickets?'),
 ('Compliance','The compliance committee meets on the first Tuesday of each quarter.','When does the compliance committee meet?'),
 ('Finance','Quarterly financial forecasts are submitted to the CFO by the fifth business day.','Who receives the quarterly finance forecasts?'),
 ('Inventory','Asset inventory reconciliation takes place on the final Friday of each month.','When does the asset inventory get reconciled?'),
 ('Engineering','Pull requests require successful unit tests and static analysis before merging.','What automated checks must pass before code merges?'),
 ('Operations','On call engineers rotate weekly every Monday at 9 AM Central time.','What time does the engineer on call handover happen?'),
 ('Legal','Contracts with automatic renewal require legal review 60 days before renewal.','How far ahead does legal review auto renewing contracts?'),
 ('Product','Customer feature proposals undergo product discovery before roadmap prioritization.','What happens before a feature enters roadmap ranking?'),
 ('Privacy','Data subject access requests must be acknowledged within 3 business days.','How soon must privacy access requests be acknowledged?'),
 ('Marketing','Public press statements require communications team review before publication.','Who reviews press releases before publishing?'),
 ('Facilities','Building visitor badges expire at 6 PM local time on the visit day.','When does a visitor pass become invalid?'),
 ('Sales','Enterprise contract discounts greater than 20 percent require sales VP approval.','Who approves enterprise discounts above 20 percent?'),
 ('Quality','Regression test suites are executed nightly on the integration branch.','How often do full regression suites run?'),
 ('HR','Employee leave requests should be submitted at least 10 business days ahead.','How early should staff submit leave requests?'),
 ('Analytics','Analytics dashboard data refresh occurs every morning at 5 AM UTC.','When is the reporting dashboard refreshed?'),
]

def run():
    os.environ['EMBEDDING_PROVIDER']='local'
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(str(Path(tmp)/'bench.db'),embed_local)
        ids={}
        for title,body,q in DATA:
            ids[title]=store.ingest('benchmark',title,body)['document_id']
        summary={}
        for mode in ('lexical','vector','hybrid'):
            hits1=hits3=0;mrr=0;timings=[];ranks=[]
            for title,body,q in DATA:
                start=time.perf_counter()
                found=store.search('benchmark',q,k=3,mode=mode)
                timings.append((time.perf_counter()-start)*1000)
                order=[h.document_id for h in found]
                pos=order.index(ids[title])+1 if ids[title] in order else None
                hits1+=int(pos==1);hits3+=int(pos is not None)
                mrr+=1/pos if pos else 0
                ranks.append({'query':q,'relevant_document':title,'rank_at_3':pos})
            summary[mode]={'queries':len(DATA),'recall_at_1':round(hits1/len(DATA),4),'recall_at_3':round(hits3/len(DATA),4),
                'mrr_at_3':round(mrr/len(DATA),4),'median_retrieval_ms':round(statistics.median(timings),3),
                'p95_retrieval_ms':round(sorted(timings)[int(.95*(len(timings)-1))],3), 'per_query':ranks}
        result={'benchmark':'synthetic_policy_retrieval_v1','seed':'fixed_dataset_no_randomness','embedding':'local deterministic hash features, not neural semantic embedding',
          'dataset_documents':len(DATA),'dataset_queries':len(DATA),'python':platform.python_version(),
          'measurement':'Single-process end-to-end retrieval, excludes ingestion, HTTP, LLM calls, and user-facing answer quality',
          'results':summary}
        out=Path(__file__).parent/'results.json';out.write_text(json.dumps(result,indent=2)+'\n')
        for mode,info in summary.items():print(f"{mode:8} Recall@1={info['recall_at_1']:.1%} Recall@3={info['recall_at_3']:.1%} MRR@3={info['mrr_at_3']:.3f} p50={info['median_retrieval_ms']:.2f}ms p95={info['p95_retrieval_ms']:.2f}ms")
if __name__=='__main__':run()
