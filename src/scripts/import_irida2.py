from io import StringIO
from pprint import pformat
from typing import Any
from pandas import DataFrame
from tools import Settings
from sqlalchemy.orm import Session
from pathlib import Path
import logging, numpy as np, sys, re, json, pandas as pd
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from sqlalchemy.exc import IntegrityError
from datetime import datetime


logger = logging.getLogger(f"submissions.{__name__}")

modes = dict(
    contains=["contains_ratio", "contains_hashes"],
    matches=["matches_ratio", "matches_hashes"],
    kraken=["kraken_percent", "kraken_count"]
)


def read_tsv(filein: str | Path) -> str:
    """
    Reads a tsv file into string

    Args:
        filein (str): path to the tsv file

    Returns:
        str: tsv file contents as string
    """
    if isinstance(filein, str):
        filein = Path(filein)
    if filein.exists:
        with open(filein, "r") as f:
            text = f.read()
        return text
    else:
        logger.error(f"Could not find tsv file at {filein}. Returning None.")
        return None


def write_output(filename: Path, output: str):
    """
    Writes to file. Takes care of decoding.

    Args:
        filename (Path): File to write to.
        output (str): Content to write.
    """
    with open(filename.__str__(), "w") as f:
        logger.debug(f"Writing to {filename}")
        try:
            output = output.decode("utf-8")
        except AttributeError as e:
            logger.error(f"Output string was not byteslike object.")
        f.write(output)


def get_all_control_sample_names_if_mode_not_empty(ctx: Settings, session: Session, mode: str) -> list:
    """
    Grabs all control sample names from the db if the mode field is not empty.
    Used for eliminating already seen sample from processing.

    Args:
        settings (dict): settings passed down from click. Defaults to {}.

    Returns:
        list: names list
    """
    from backend.db import IridaControl
    logger.debug("Going into query.")
    # new_session = Session(ctx.database_session.get_bind())
    samples = session.query(IridaControl).all()
    samples = [sample.name for sample in samples if not getattr(sample, mode) is None]
    # new_session.close()
    return samples


def lookup_sample(ctx: Settings, session: Session, submitter_id: str):
    from backend.db import Sample
    sample = session.query(Sample).filter(Sample.sample_id == submitter_id).first()
    # new_session.close()
    return sample


def check_folders_against_database(ctx: Settings, session: Session, mode: str, ):
    db_samples = get_all_control_sample_names_if_mode_not_empty(ctx=ctx, session=session, mode=mode)
    project_dir = Path(ctx.directory_path).joinpath("submissions_parser_output",
                                                    "Robotics Support Laboratory Extraction Controls")
    db_samples = [project_dir.joinpath(sample).__str__() for sample in db_samples]
    # logger.debug(db_samples)
    folder_samples = [sample.__str__() for sample in project_dir.iterdir() if sample.is_dir()]
    # samples_of_interest = np.setdiff1d(folder_samples, db_samples)
    samples_of_interest = np.setdiff1d(folder_samples, db_samples)
    return [Path(sample) for sample in samples_of_interest]


def enforce_naming_schema(instr: str) -> str:
    """
    Function to fix naming format mistakes from whoever is doing the Irida inputs.

    Args:
        instr (str): input sample name

    Returns:
        str: fixed sample name
    """
    instr = re.sub(r"^(ATCC)-?(\d{5})(-\d{3})(-\d{8})?(-\d{3}bp)?", r"\1\2\3\4\5",
                   instr)  #: <start>("ATCC")(maybe "-")(five digits)("-" + three digits)(maybe "-" + eight digits)(maybe three digits + "bp")
    return instr


def parse_control_type_from_name(ctx: Settings, control_name: str) -> str:
    """
    Checks for control type in string. Uses joined ct_type_regexes defined in config.yml and pulled into settings.

    Args:
        settings (dict): Settings passed down from click.
        control_name (str): Sample name

    Returns:
        str: Parsed control type.
    """
    temp = construct_type_regexes(ctx=ctx)
    # logger.debug(f"Attempting to parse using regex: {temp}")
    # Note: matches here does not refer to the mode matches, but regex pattern matches.
    matches = re.match(temp, control_name)
    # logger.debug(f"Regex matches: {matches}")
    try:
        ct_type = [item for item in matches.groupdict().keys() if matches.groupdict()[item] != None][0]
    except AttributeError as e:
        return None
    return ct_type


def construct_type_regexes(ctx: Settings) -> str:
    """
    Builds one big regex from all regexes in config.yml['control_types']

    Args:
        settings (dict): settings passed down from click

    Returns:
        str: large regex
    """
    # regexes = []
    # for item in settings['control_types']:
    #     rel = settings['control_types'][item]
    #     try:
    #         regexes.append(fr"{rel['regex']}")
    #     except KeyError:
    #         logger.error(f"{item} has no regex associated. Attempting to construct from control type name.")
    #         regexes.append(fr"(?P<{item.replace('-', '_')}>{item.split('-')[0]}-?[0-9a-zA-Z_]+)" + r"(?:-\d{8})?")
    regexes = [
        r"ATCC-?49226(?:-\d{3})?",
        r"ATCC-?49619(?:-\d{3})?",
        r"MCS-[a-z|A-Z]+20\d{2}P(late)?\d",
        r"MCS-(?:\d{3})",
        r"EN(1)?-(?:\d{3})",
        r"EN(1)?-[a-z|A-Z]+20\d{2}P(late)?\d",
        r"SN(1)?-[a-z|A-Z]+20\d{2}P(late)?\d",
        r"SN(1)?-(?:\d{3})"
    ]
    # I have no idea what the line below is doing, but it works.
    return '(?:% s)' % '|'.join(regexes)


def read_tsv_string(string_in: str) -> DataFrame:
    """
    Reads tsv string from memory

    Args:
        string_in (str): tsv data.

    Returns:
        DataFrame: data out
    """
    logger.debug(f"TSV string in: {type(string_in)}")
    try:
        string_in = StringIO(string_in)
    except TypeError as e:
        string_in = StringIO(string_in.decode("utf-8"))
    try:
        return pd.read_csv(string_in, sep="\t")
    except pd.errors.EmptyDataError as e:
        logger.error(f"Got empty tsv file. Returning empty dataframe.")
        return DataFrame()


def save_object(ctx:Settings, session: Session, object: Any):
    """
    Write function for control object.

    Args:
        control (IridaControl): IridaControl object to add to db.
        settings (dict): settings passed down from click. Defaults to {}.
    """

    # new_session = Session(ctx.database_session.get_bind())
    session.add(object)
    try:
        logger.debug("Commiting session.")
        session.commit()
    except (SQLOperationalError, SQLIntegrityError, IntegrityError) as e:
        logger.critical(f"Couldn't add control to db due to : {e}")
        session.rollback()
    # new_session.close()


def import_irida2(ctx: Settings):
    # Note: Does not seem to work.
    from backend.db import IridaControl, ControlType
    # new_session = Session(ctx.database_session.get_bind())
    new_session = ctx.database.session
    folders = check_folders_against_database(ctx=ctx, session=new_session, mode="kraken")
    for folder in folders:
        # logger.debug(folder)
        parsed_json = folder.joinpath("parsed.json")
        if not parsed_json.exists():
            continue
        with open(parsed_json, "r") as f:
            control_dict = json.load(f)
        control_dict['name'] = enforce_naming_schema(folder.name)
        # control_dict['controltype_name'] = parse_control_type_from_name(ctx=ctx, control_name=control_dict['name'])
        control_dict['controltype'] = ControlType.query(name="Irida Control")
        control_dict['controltype_name'] = control_dict['controltype'].name
        control_dict['submitted_date'] = datetime.strptime(control_dict['submitted_date'], "%Y-%m-%d")
        logger.debug(f"Sample:\n{pformat(control_dict)}")
        new_control = IridaControl(**control_dict)
        logger.debug(new_control)
        for mode in modes:
            tsv_file = Path(folder).joinpath(f"{control_dict['name']}_{mode}.tsv")
            if Path(tsv_file).exists():
                logger.debug(f"Existing tsv file: {tsv_file}, reading...")
                tsv_text = read_tsv(tsv_file)
            elif Path(folder).joinpath(f"{mode}.tsv").exists():
                tsv_text = read_tsv(Path(folder).joinpath(f"{mode}.tsv"))
                write_output(tsv_file, tsv_text)
            else:
                logger.error(f"No tsv file found for {mode}, skipping.")
                continue
            if tsv_text is None:
                logger.error(f"Failed to write {mode}.tsv file due to error, skipping.")
                continue
            try:
                reads_json = read_tsv_string(tsv_text).T.to_dict()
            except AttributeError as e:
                logger.warning(f"The {mode} file for {folder} must have been empty. Using empty dict.")
                reads_json = {}
            new_control.__setattr__(mode, reads_json)
            sample = lookup_sample(ctx=ctx, session=new_session, submitter_id=control_dict['name'])
            if sample is not None:
                logger.debug(f"Got sample: {sample} with submission {sample.submissions}")
                sample.control = new_control
                try:
                    new_control.clientsubmission = sample.submissions[0]
                except IndexError:
                    logger.error(f"No submissions in sample.")
                save_object(ctx=ctx, session=new_session, object=sample)
                if getattr(new_control, mode) == {} and new_control.submitted_date is None:
                    logger.warning(f"Sample {new_control.name} has no {mode} or date. Skipping")
                    continue
                else:
                    save_object(ctx=ctx, session=new_session, object=new_control)
            else:
                logger.error(f"No sample with name {control_dict['name']} found.")
