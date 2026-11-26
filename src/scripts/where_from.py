
"""
For one SubmissionType: where does each name in its info/sample order lists come from?
"""
import sys, logging
from collections import defaultdict
from datetime import date, timedelta
logging.disable(logging.CRITICAL)
import tools  # noqa: F401  (sets up ctx and the database from your config)
from backend.db.models import SubmissionType, ClientSubmission


def as_list(result):
    # NOTE: query() returns None for no match and a bare object for exactly one.
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


st = SubmissionType.query(name=sys.argv[1], limit=1)
print("STORED info  :", [i["name"] for i in st._info_exclude_order or []])
print("STORED sample:", [i["name"] for i in st._sample_exclude_order or []])

submissions = as_list(ClientSubmission.query(start_date=date.today() - timedelta(days=30), submissiontype=st.name))
print(f"\n{len(submissions)} submission(s) in the last 30 days")
sources = defaultdict(set)
for sub in submissions:
    for key in sub.misc_info or {}:
        sources[key].add(f"ClientSubmission.misc_info  (e.g. {sub.name})")
    for assoc in sub.clientsubmissionsampleassociation:
        for key in assoc.misc_info or {}:
            sources[key].add(f"ClientSubmissionSampleAssociation.misc_info  (e.g. {assoc.sample.sample_id})")
    for sample in sub.sample:
        for key in sample.misc_info or {}:
            sources[key].add(f"Sample.misc_info  (e.g. {sample.sample_id})")
for key in sorted(sources):
    print(f"  {key:30} <- " + "; ".join(sorted(sources[key])))
