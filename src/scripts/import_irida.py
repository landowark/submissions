import logging, sqlite3, json
from pprint import pformat, pprint
from datetime import datetime
from tools import Settings

from sqlalchemy.orm import Session

logger = logging.getLogger(f"submissions.{__name__}")

def import_irida(ctx: Settings):
    """
    Grabs Irida control from secondary database.

    Args:
        ctx (Settings): Settings inherited from app.
    """
    from backend import Sample
    from backend.db import IridaControl, ControlType
    # NOTE: Because the main session will be busy in another thread, this requires a new session.
    new_session = Session(ctx.database_session.get_bind())
    ct = new_session.query(ControlType).filter(ControlType.name == "Irida Control").first()
    existing_controls = [item.name for item in new_session.query(IridaControl)]
    prm_list = ", ".join([f"'{thing}'" for thing in existing_controls])
    ctrl_db_path = ctx.directory_path.joinpath("submissions_parser_output", "procedure.db")
    try:
        conn = sqlite3.connect(ctrl_db_path)
    except AttributeError as e:
        logger.error(f"Error, could not import from irida due to {e}")
        return
    sql = "SELECT name, submitted_date, procedure_id, contains, matches, kraken, subtype, refseq_version, " \
          "kraken2_version, kraken2_db_version, sample_id FROM _iridacontrol INNER JOIN _control on _control.id " \
          f"= _iridacontrol.id WHERE _control.name NOT IN ({prm_list})"
    cursor = conn.execute(sql)
    records = [
        dict(name=row[0], submitted_date=row[1], submission_id=row[2], contains=row[3], matches=row[4], kraken=row[5],
             subtype=row[6], refseq_version=row[7], kraken2_version=row[8], kraken2_db_version=row[9],
             sample_id=row[10]) for row in cursor]
    for record in records:
        instance = new_session.query(IridaControl).filter(IridaControl.name == record['name']).first()
        if instance:
            logger.warning(f"Irida Control {instance.name} already exists, skipping.")
            continue
        for thing in ['contains', 'matches', 'kraken']:
            if record[thing]:
                record[thing] = json.loads(record[thing])
                assert isinstance(record[thing], dict)
            else:
                record[thing] = {}
        record['submitted_date'] = datetime.strptime(record['submitted_date'], "%Y-%m-%d %H:%M:%S.%f")
        assert isinstance(record['submitted_date'], datetime)
        instance = IridaControl(controltype=ct, **record)
        sample = new_session.query(Sample).filter(Sample.sample_id == instance.name).first()
        if sample:
            instance.sample = sample
            try:
                instance.clientsubmission = sample.procedure[0]
            except IndexError:
                logger.error(f"Could not get sample for {sample}")
                instance.clientsubmission = None
            # instance.procedure = sample.procedure[0]
        new_session.add(instance)
    new_session.commit()
    new_session.close()
