'''
Convenience functions for interacting with the database.
'''

from . import models
# from .models.kits import KitType
# from .models.submissions import BasicSample, reagents_submissions, BasicSubmission, SubmissionSampleAssociation
# from .models import submissions
import pandas as pd
import sqlalchemy.exc
import sqlite3
import logging
from datetime import date, datetime, timedelta
from sqlalchemy import and_, JSON, event
from sqlalchemy.exc import IntegrityError, OperationalError, SAWarning
from sqlalchemy.engine import Engine
import json
from getpass import getuser
import numpy as np
import yaml
from pathlib import Path
from tools import Settings, check_regex_match, RSLNamer
from typing import List



logger = logging.getLogger(f"submissions.{__name__}")

# The below _should_ allow automatic creation of foreign keys in the database
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def store_submission(ctx:Settings, base_submission:models.BasicSubmission, samples:List[dict]=[]) -> None|dict:
    """
    Upserts submissions into database

    Args:
        ctx (Settings): settings object passed down from gui
        base_submission (models.BasicSubmission): submission to be add to db

    Returns:
        None|dict : object that indicates issue raised for reporting in gui
    """    
    logger.debug(f"Hello from store_submission")
    # Add all samples to sample table
    typer = RSLNamer(ctx=ctx, instr=base_submission.rsl_plate_num)
    base_submission.rsl_plate_num = typer.parsed_name
    # for sample in samples:
    #     instance = sample['sample']
    #     logger.debug(f"Typer: {typer.submission_type}")
    #     logger.debug(f"sample going in: {type(sample['sample'])}\n{sample['sample'].__dict__}")
    #     # Suuuuuper hacky way to be sure that the artic doesn't overwrite the ww plate in a ww sample
    #     # need something more elegant
    #     # if "_artic" not in typer.submission_type:
    #     #     sample.rsl_plate = base_submission
    #     # else:
    #     #     logger.debug(f"{sample.ww_sample_full_id} is an ARTIC sample.")
    #     #     # base_submission.samples.remove(sample)
    #     #     # sample.rsl_plate = sample.rsl_plate
    #     #     # sample.artic_rsl_plate = base_submission
    #     # logger.debug(f"Attempting to add sample: {sample.to_string()}")
    #     # try:
    #         # ctx['database_session'].add(sample)
    #     # ctx.database_session.add(instance)
    #     # ctx.database_session.commit()
    #     # logger.debug(f"Submitter id: {sample['sample'].submitter_id} and table id: {sample['sample'].id}")
    #     logger.debug(f"Submitter id: {instance.submitter_id} and table id: {instance.id}")
    #     assoc = SubmissionSampleAssociation(submission=base_submission, sample=instance, row=sample['row'], column=sample['column'])
        
    #     # except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
    #     #     logger.debug(f"Hit an integrity error : {e}")
    #     #     continue
    #     try:
    #         base_submission.submission_sample_associations.append(assoc)
    #     except IntegrityError as e:
    #         logger.critical(e)
    #         continue
        # logger.debug(f"Here is the sample to be stored in the DB: {sample.__dict__}")
    # Add submission to submission table
    # ctx['database_session'].add(base_submission)
    ctx.database_session.add(base_submission)
    logger.debug(f"Attempting to add submission: {base_submission.rsl_plate_num}")
    try:
        # ctx['database_session'].commit()
        ctx.database_session.commit()
    except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
        logger.debug(f"Hit an integrity error : {e}")
        # ctx['database_session'].rollback()
        ctx.database_session.rollback()
        return {"message":"This plate number already exists, so we can't add it.", "status":"Critical"}
    except (sqlite3.OperationalError, sqlalchemy.exc.IntegrityError) as e:
        logger.debug(f"Hit an operational error: {e}")
        # ctx['database_session'].rollback()
        ctx.database_session.rollback()
        return {"message":"The database is locked for editing.", "status":"Critical"}
    return None

def store_reagent(ctx:Settings, reagent:models.Reagent) -> None|dict:
    """
    Inserts a reagent into the database.

    Args:
        ctx (Settings): settings object passed down from gui
        reagent (models.Reagent): Reagent object to be added to db

    Returns:
        None|dict: object indicating issue to be reported in the gui
    """    
    logger.debug(f"Reagent dictionary: {reagent.__dict__}")
    # ctx['database_session'].add(reagent)
    ctx.database_session.add(reagent)
    try:
        # ctx['database_session'].commit()
        ctx.database_session.commit()
    except (sqlite3.OperationalError, sqlalchemy.exc.OperationalError):
        return {"message":"The database is locked for editing."}
    return None

def construct_submission_info(ctx:Settings, info_dict:dict) -> models.BasicSubmission:
    """
    Construct submission object from dictionary

    Args:
        ctx (Settings): settings object passed down from gui
        info_dict (dict): dictionary to be transformed

    Returns:
        models.BasicSubmission: Constructed submission object
    """
    # from tools import check_regex_match, RSLNamer
    # convert submission type into model name
    query = info_dict['submission_type'].replace(" ", "")
    # Ensure an rsl plate number exists for the plate
    if not check_regex_match("^RSL", info_dict["rsl_plate_num"]):
        instance = None
        msg = "A proper RSL plate number is required."
        return instance, {'code': 2, 'message': "A proper RSL plate number is required."}
    else:
        # enforce conventions on the rsl plate number from the form
        info_dict['rsl_plate_num'] = RSLNamer(ctx=ctx, instr=info_dict["rsl_plate_num"]).parsed_name
    # check database for existing object
    # instance = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==info_dict['rsl_plate_num']).first()
    # instance = ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==info_dict['rsl_plate_num']).first()
    instance = lookup_submission_by_rsl_num(ctx=ctx, rsl_num=info_dict['rsl_plate_num'])
    # get model based on submission type converted above
    logger.debug(f"Looking at models for submission type: {query}")
    model = getattr(models, query)
    logger.debug(f"We've got the model: {type(model)}")
    info_dict['submission_type'] = info_dict['submission_type'].replace(" ", "_").lower()
    # if query return nothing, ie doesn't already exist in db
    if instance == None:
        instance = model()
        logger.debug(f"Submission doesn't exist yet, creating new instance: {instance}")
        msg = None
        code = 0
    else:
        code = 1
        msg = "This submission already exists.\nWould you like to overwrite?"
    for item in info_dict:
        value = info_dict[item]
        logger.debug(f"Setting {item} to {value}")
        # set fields based on keys in dictionary
        match item:
            case "extraction_kit":
                # q_str = info_dict[item]
                logger.debug(f"Looking up kit {value}")
                try:
                    field_value = lookup_kittype_by_name(ctx=ctx, name=value)
                except (sqlite3.IntegrityError, sqlalchemy.exc.IntegrityError) as e:
                    logger.error(f"Hit an integrity error looking up kit type: {e}")
                    logger.error(f"Details: {e.__dict__}")
                    if "submitter_plate_num" in e.__dict__['statement']:
                        msg = "SQL integrity error. Submitter plate id is a duplicate or invalid."
                    else:
                        msg = "SQL integrity error of unknown origin."
                    return instance, dict(code=2, message=msg)
                logger.debug(f"Got {field_value} for kit {value}")
            case "submitting_lab":
                value = value.replace(" ", "_").lower()
                logger.debug(f"Looking up organization: {value}")
                field_value = lookup_org_by_name(ctx=ctx, name=value)
                logger.debug(f"Got {field_value} for organization {value}")
            case "submitter_plate_num":
                # Because of unique constraint, there will be problems with 
                # multiple submissions named 'None', so...
                # Should be depreciated with use of pydantic validator
                logger.debug(f"Submitter plate id: {value}")
                # if info_dict[item] == None or info_dict[item] == "None" or info_dict[item] == "":
                #     logger.debug(f"Got None as a submitter plate number, inserting random string to preserve database unique constraint.")
                #     info_dict[item] = uuid.uuid4().hex.upper()
                field_value = value
            case "samples":
                for sample in value:
                    sample_instance = lookup_sample_by_submitter_id(ctx=ctx, submitter_id=sample['sample'].submitter_id)
                    if sample_instance == None:
                        sample_instance = sample['sample']
                    else:
                        logger.warning(f"Sample {sample} already exists, creating association.")
                    if sample_instance in instance.samples:
                        logger.error(f"Looks like there's a duplicate sample on this plate: {sample_instance.submitter_id}!")
                        continue
                    try:
                        with ctx.database_session.no_autoflush:
                            try:
                                logger.debug(f"Here is the sample instance type: {sample_instance.sample_type}")
                                try:
                                    assoc = getattr(models, f"{sample_instance.sample_type.replace('_sample', '').replace('_', ' ').title().replace(' ', '')}Association")
                                except AttributeError as e:
                                    assoc = models.SubmissionSampleAssociation
                                # assoc = models.SubmissionSampleAssociation(submission=instance, sample=sample_instance, row=sample['row'], column=sample['column'])
                                assoc = assoc(submission=instance, sample=sample_instance, row=sample['row'], column=sample['column'])
                                instance.submission_sample_associations.append(assoc)
                            except IntegrityError:
                                logger.error(f"Hit integrity error for: {sample}")
                                continue
                            except SAWarning:
                                logger.error(f"Looks like the association already exists for submission: {instance} and sample: {sample_instance}")
                                continue
                    except IntegrityError as e:
                        logger.critical(e)
                        continue
                continue
            case _:
                field_value = value
        # insert into field
        try:
            setattr(instance, item, field_value)
        except AttributeError:
            logger.debug(f"Could not set attribute: {item} to {info_dict[item]}")
            continue
        except KeyError:
            continue
    # calculate cost of the run: immutable cost + mutable times number of columns
    # This is now attached to submission upon creation to preserve at-run costs incase of cost increase in the future.
    try:
        # ceil(instance.sample_count / 8) will get number of columns
        # the cost of a full run multiplied by (that number / 12) is x twelfths the cost of a full run
        logger.debug(f"Calculating costs for procedure...")
        instance.calculate_base_cost()
    except (TypeError, AttributeError) as e:
        logger.debug(f"Looks like that kit doesn't have cost breakdown yet due to: {e}, using full plate cost.")
        instance.run_cost = instance.extraction_kit.cost_per_run
    logger.debug(f"Calculated base run cost of: {instance.run_cost}")
    try:
        logger.debug("Checking and applying discounts...")
        discounts = [item.amount for item in lookup_discounts_by_org_and_kit(ctx=ctx, kit_id=instance.extraction_kit.id, lab_id=instance.submitting_lab.id)]
        logger.debug(f"We got discounts: {discounts}")
        if len(discounts) > 0:
            discounts = sum(discounts)
            instance.run_cost = instance.run_cost - discounts
    except Exception as e:
        logger.error(f"An unknown exception occurred when calculating discounts: {e}")
    # We need to make sure there's a proper rsl plate number
    logger.debug(f"We've got a total cost of {instance.run_cost}")
    try:
        logger.debug(f"Constructed instance: {instance.to_string()}")
    except AttributeError as e:
        logger.debug(f"Something went wrong constructing instance {info_dict['rsl_plate_num']}: {e}")
    logger.debug(f"Constructed submissions message: {msg}")
    return instance, {'code':code, 'message':msg}
    
def construct_reagent(ctx:Settings, info_dict:dict) -> models.Reagent:
    """
    Construct reagent object from dictionary

    Args:
        ctx (Settings): settings object passed down from gui
        info_dict (dict): dictionary to be converted

    Returns:
        models.Reagent: Constructed reagent object
    """    
    reagent = models.Reagent()
    for item in info_dict:
        logger.debug(f"Reagent info item: {item}")
        # set fields based on keys in dictionary
        match item:
            case "lot":
                reagent.lot = info_dict[item].upper()
            case "expiry":
                reagent.expiry = info_dict[item]
            case "type":
                reagent.type = lookup_reagenttype_by_name(ctx=ctx, rt_name=info_dict[item].replace(" ", "_").lower())
    # add end-of-life extension from reagent type to expiry date
    # NOTE: this will now be done only in the reporting phase to account for potential changes in end-of-life extensions
    # try:
    #     reagent.expiry = reagent.expiry + reagent.type.eol_ext
    # except TypeError as e:
    #     logger.debug(f"We got a type error: {e}.")
    # except AttributeError:
    #     pass
    return reagent

def get_all_reagenttype_names(ctx:Settings) -> list[str]:
    """
    Lookup all reagent types and get names

    Args:
        ctx (Settings): settings object passed from gui

    Returns:
        list[str]: reagent type names
    """    
    # lookedup = [item.__str__() for item in ctx['database_session'].query(models.ReagentType).all()]
    lookedup = [item.__str__() for item in ctx.database_session.query(models.ReagentType).all()]
    return lookedup

def lookup_reagenttype_by_name(ctx:Settings, rt_name:str) -> models.ReagentType:
    """
    Lookup a single reagent type by name

    Args:
        ctx (Settings): settings object passed from gui
        rt_name (str): reagent type name to look up

    Returns:
        models.ReagentType: looked up reagent type
    """    
    logger.debug(f"Looking up ReagentType by name: {rt_name}")
    # lookedup = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==rt_name).first()
    lookedup = ctx.database_session.query(models.ReagentType).filter(models.ReagentType.name==rt_name).first()
    logger.debug(f"Found ReagentType: {lookedup}")
    return lookedup

def lookup_kittype_by_use(ctx:Settings, used_by:str|None=None) -> list[models.KitType]:
    """
    Lookup kits by a sample type its used for

    Args:
        ctx (Settings): settings object from gui
        used_by (str): sample type (should be string in D3 of excel sheet)

    Returns:
        list[models.KitType]: list of kittypes that have that sample type in their uses
    """    
    if used_by != None:
        # return ctx['database_session'].query(models.KitType).filter(models.KitType.used_for.contains(used_by)).all()
        return ctx.database_session.query(models.KitType).filter(models.KitType.used_for.contains(used_by)).all()
    else:
        # return ctx['database_session'].query(models.KitType).all()
        return ctx.database_session.query(models.KitType).all()

def lookup_kittype_by_name(ctx:Settings, name:str) -> models.KitType:
    """
    Lookup a kit type by name

    Args:
        ctx (Settings): settings object passed from bui
        name (str): name of kit to query

    Returns:
        models.KitType: retrieved kittype
    """    
    if isinstance(name, dict):
        name = name['value']
    logger.debug(f"Querying kittype: {name}")
    # return ctx['database_session'].query(models.KitType).filter(models.KitType.name==name).first()
    return ctx.database_session.query(models.KitType).filter(models.KitType.name==name).first()
    
def lookup_kittype_by_id(ctx:Settings, id:int) -> models.KitType:
    return ctx.database_session.query(models.KitType).filter(models.KitType.id==id).first()

def lookup_regent_by_type_name(ctx:Settings, type_name:str) -> list[models.Reagent]:
    """
    Lookup reagents by their type name

    Args:
        ctx (Settings): settings object passed from gui
        type_name (str): reagent type name

    Returns:
        list[models.Reagent]: list of retrieved reagents
    """    
    # return ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).all()
    return ctx.database_session.query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).all()

def lookup_regent_by_type_name_and_kit_name(ctx:Settings, type_name:str, kit_name:str) -> list[models.Reagent]:
    """
    Lookup reagents by their type name and kits they belong to (Broken... maybe cursed, I'm not sure.)

    Args:
        ctx (Settings): settings object pass by gui
        type_name (str): reagent type name
        kit_name (str): kit name

    Returns:
        list[models.Reagent]: list of retrieved reagents
    """    
    # What I want to do is get the reagent type by name 
    # Hang on, this is going to be a long one.
    # by_type = ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name.endswith(type_name)).all()
    # rt_types = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name.endswith(type_name))
    rt_types = ctx.database_session.query(models.ReagentType).filter(models.ReagentType.name.endswith(type_name))
    # add filter for kit name... 
    try:
        check = not np.isnan(kit_name)
    except TypeError:
        check = True
    if check:
        kit_type = lookup_kittype_by_name(ctx=ctx, name=kit_name)
        logger.debug(f"reagenttypes: {[item.name for item in rt_types.all()]}, kit: {kit_type.name}")
        # add in lookup for related kit_id
        rt_types = rt_types.join(reagenttypes_kittypes).filter(reagenttypes_kittypes.c.kits_id==kit_type.id).first()
    else:
        rt_types = rt_types.first()
    output = rt_types.instances
    return output

def lookup_all_submissions_by_type(ctx:Settings, sub_type:str|None=None) -> list[models.BasicSubmission]:
    """
    Get all submissions, filtering by type if given

    Args:
        ctx (Settings): settings object pass from gui
        type (str | None, optional): submission type (should be string in D3 of excel sheet). Defaults to None.

    Returns:
        list[models.BasicSubmission]: list of retrieved submissions
    """
    if sub_type == None:
        # subs = ctx['database_session'].query(models.BasicSubmission).all()
        subs = ctx.database_session.query(models.BasicSubmission).all()
    else:
        # subs = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.submission_type==sub_type.lower().replace(" ", "_")).all()
        subs = ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.submission_type==sub_type.lower().replace(" ", "_")).all()
    return subs

def lookup_all_orgs(ctx:Settings) -> list[models.Organization]:
    """
    Lookup all organizations (labs)

    Args:
        ctx (Settings): settings object passed from gui

    Returns:
        list[models.Organization]: list of retrieved organizations
    """    
    # return ctx['database_session'].query(models.Organization).all()
    return ctx.database_session.query(models.Organization).all()

def lookup_org_by_name(ctx:Settings, name:str|None) -> models.Organization:
    """
    Lookup organization (lab) by (startswith) name.

    Args:
        ctx (Settings): settings passed from gui
        name (str | None): name of organization

    Returns:
        models.Organization: retrieved organization
    """    
    logger.debug(f"Querying organization: {name}")
    # return ctx['database_session'].query(models.Organization).filter(models.Organization.name.startswith(name)).first()
    return ctx.database_session.query(models.Organization).filter(models.Organization.name.startswith(name)).first()

def submissions_to_df(ctx:Settings, sub_type:str|None=None) -> pd.DataFrame:
    """
    Convert submissions looked up by type to dataframe

    Args:
        ctx (Settings): settings object passed by gui
        type (str | None, optional): submission type (should be string in D3 of excel sheet) Defaults to None.

    Returns:
        pd.DataFrame: dataframe constructed from retrieved submissions
    """    
    logger.debug(f"Type: {sub_type}")
    # use lookup function to create list of dicts
    subs = [item.to_dict() for item in lookup_all_submissions_by_type(ctx=ctx, sub_type=sub_type)]
    # make df from dicts (records) in list
    df = pd.DataFrame.from_records(subs)
    # Exclude sub information
    try:
        df = df.drop("controls", axis=1)
    except:
        logger.warning(f"Couldn't drop 'controls' column from submissionsheet df.")
    try:
        df = df.drop("ext_info", axis=1)
    except:
        logger.warning(f"Couldn't drop 'ext_info' column from submissionsheet df.")
    try:
        df = df.drop("pcr_info", axis=1)
    except:
        logger.warning(f"Couldn't drop 'pcr_info' column from submissionsheet df.")
    return df
    
def lookup_submission_by_id(ctx:Settings, id:int) -> models.BasicSubmission:
    """
    Lookup submission by id number

    Args:
        ctx (Settings): settings object passed from gui
        id (int): submission id number

    Returns:
        models.BasicSubmission: retrieved submission
    """    
    # return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()
    return ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()

def lookup_submissions_by_date_range(ctx:Settings, start_date:datetime.date, end_date:datetime.date) -> list[models.BasicSubmission]:
    """
    Lookup submissions greater than start_date and less than end_date

    Args:
        ctx (Settings): settings object passed from gui
        start_date (datetime.date): date to start looking
        end_date (datetime.date): date to end looking

    Returns:
        list[models.BasicSubmission]: list of retrieved submissions
    """    
    # return ctx['database_session'].query(models.BasicSubmission).filter(and_(models.BasicSubmission.submitted_date > start_date, models.BasicSubmission.submitted_date < end_date)).all()
    start_date = start_date.strftime("%Y-%m-%d")
    end_date = end_date.strftime("%Y-%m-%d")
    # return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.submitted_date.between(start_date, end_date)).all()
    return ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.submitted_date.between(start_date, end_date)).all()

def get_all_Control_Types_names(ctx:Settings) -> list[str]:
    """
    Grabs all control type names from db.

    Args:
        settings (Settings): settings object passed down from gui.

    Returns:
        list: list of controltype names
    """    
    # conTypes = ctx['database_session'].query(models.ControlType).all()
    conTypes = ctx.database_session.query(models.ControlType).all()
    conTypes = [conType.name for conType in conTypes]
    logger.debug(f"Control Types: {conTypes}")
    return conTypes

def create_kit_from_yaml(ctx:Settings, exp:dict) -> dict:
    """
    Create and store a new kit in the database based on a .yml file
    TODO: split into create and store functions

    Args:
        ctx (Settings): Context object passed down from frontend
        exp (dict): Experiment dictionary created from yaml file

    Returns:
        dict: a dictionary containing results of db addition
    """    
    from tools import check_is_power_user, massage_common_reagents
    # Don't want just anyone adding kits
    if not check_is_power_user(ctx=ctx):
        logger.debug(f"{getuser()} does not have permission to add kits.")
        return {'code':1, 'message':"This user does not have permission to add kits.", "status":"warning"}
    # iterate through keys in dict
    for type in exp:
        # if type == "password":
        #     continue
        # A submission type may use multiple kits.
        for kt in exp[type]['kits']:
            kit = models.KitType(name=kt, 
                                 used_for=[type.replace("_", " ").title()], 
                                 constant_cost=exp[type]["kits"][kt]["constant_cost"], 
                                 mutable_cost_column=exp[type]["kits"][kt]["mutable_cost_column"],
                                 mutable_cost_sample=exp[type]["kits"][kt]["mutable_cost_sample"]
                                 )
            # A kit contains multiple reagent types.
            for r in exp[type]['kits'][kt]['reagenttypes']:
                # check if reagent type already exists.
                r = massage_common_reagents(r)
                # look_up = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==r).first()
                look_up = ctx.database_session.query(models.ReagentType).filter(models.ReagentType.name==r).first()
                if look_up == None:
                    # rt = models.ReagentType(name=r.replace(" ", "_").lower(), eol_ext=timedelta(30*exp[type]['kits'][kt]['reagenttypes'][r]['eol_ext']), kits=[kit], required=1)
                    rt = models.ReagentType(name=r.replace(" ", "_").lower(), eol_ext=timedelta(30*exp[type]['kits'][kt]['reagenttypes'][r]['eol_ext']), last_used="")
                else:
                    rt = look_up
                    # rt.kits.append(kit)
                    # add this because I think it's necessary to get proper back population
                    # try:
                        # kit.reagent_types_id.append(rt.id)
                    # except AttributeError as e:
                        # logger.error(f"Error appending reagent id to kit.reagent_types_id: {e}, creating new.")
                        # kit.reagent_types_id = [rt.id]
                assoc = models.KitTypeReagentTypeAssociation(kit_type=kit, reagent_type=rt, uses=kit.used_for)
                # ctx['database_session'].add(rt)
                ctx.database_session.add(rt)
                kit.kit_reagenttype_associations.append(assoc)
                logger.debug(f"Kit construction reagent type: {rt.__dict__}")
            logger.debug(f"Kit construction kit: {kit.__dict__}")
        # ctx['database_session'].add(kit)
        ctx.database_session.add(kit)
    # ctx['database_session'].commit()
    ctx.database_session.commit()
    return {'code':0, 'message':'Kit has been added', 'status': 'information'}

def create_org_from_yaml(ctx:Settings, org:dict) -> dict:
    """
    Create and store a new organization based on a .yml file

    Args:
        ctx (Settings): Context object passed down from frontend
        org (dict): Dictionary containing organization info.

    Returns:
        dict: dictionary containing results of db addition
    """    
    from tools import check_is_power_user
    # Don't want just anyone adding in clients
    if not check_is_power_user(ctx=ctx):
        logger.debug(f"{getuser()} does not have permission to add kits.")
        return {'code':1, 'message':"This user does not have permission to add organizations."}
    # the yml can contain multiple clients
    for client in org:
        cli_org = models.Organization(name=client.replace(" ", "_").lower(), cost_centre=org[client]['cost centre'])
        # a client can contain multiple contacts
        for contact in org[client]['contacts']:
            cont_name = list(contact.keys())[0]
            # check if contact already exists
            # look_up = ctx['database_session'].query(models.Contact).filter(models.Contact.name==cont_name).first()
            look_up = ctx.database_session.query(models.Contact).filter(models.Contact.name==cont_name).first()
            if look_up == None:
                cli_cont = models.Contact(name=cont_name, phone=contact[cont_name]['phone'], email=contact[cont_name]['email'], organization=[cli_org])
            else:
                cli_cont = look_up
                cli_cont.organization.append(cli_org)
            # ctx['database_session'].add(cli_cont)
            ctx.database_session.add(cli_cont)
            logger.debug(f"Client creation contact: {cli_cont.__dict__}")
        logger.debug(f"Client creation client: {cli_org.__dict__}")
        # ctx['database_session'].add(cli_org)
        ctx.database_session.add(cli_org)
    # ctx["database_session"].commit()
    ctx.database_session.commit()
    return {"code":0, "message":"Organization has been added."}

def lookup_all_sample_types(ctx:Settings) -> list[str]:
    """
    Lookup all sample types and get names

    Args:
        ctx (Settings): settings object pass from gui

    Returns:
        list[str]: list of sample type names
    """    
    # uses = [item.used_for for item in ctx['database_session'].query(models.KitType).all()]
    uses = [item.used_for for item in ctx.database_session.query(models.KitType).all()]
    # flattened list of lists
    uses = list(set([item for sublist in uses for item in sublist]))
    return uses

def get_all_available_modes(ctx:Settings) -> list[str]:
    """
    Get types of analysis for controls

    Args:
        ctx (Settings): settings object passed from gui

    Returns:
        list[str]: list of analysis types
    """    
    # Only one control is necessary since they all share the same control types.
    # rel = ctx['database_session'].query(models.Control).first()
    rel = ctx.database_session.query(models.Control).first()
    try:
        cols = [item.name for item in list(rel.__table__.columns) if isinstance(item.type, JSON)]
    except AttributeError as e:
        logger.debug(f"Failed to get available modes from db: {e}")
        cols = []
    return cols

def get_all_controls_by_type(ctx:Settings, con_type:str, start_date:date|None=None, end_date:date|None=None) -> list[models.Control]:
    """
    Returns a list of control objects that are instances of the input controltype.
    Between dates if supplied.

    Args:
        ctx (Settings): Settings object passed down from gui
        con_type (str): Name of control type.
        start_date (date | None, optional): Start date of query. Defaults to None.
        end_date (date | None, optional): End date of query. Defaults to None.

    Returns:
        list[models.Control]: list of control samples.
    """    
    logger.debug(f"Using dates: {start_date} to {end_date}")
    if start_date != None and end_date != None:
        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")
        # output = ctx['database_session'].query(models.Control).join(models.ControlType).filter_by(name=con_type).filter(models.Control.submitted_date.between(start_date, end_date)).all()
        output = ctx.database_session.query(models.Control).join(models.ControlType).filter_by(name=con_type).filter(models.Control.submitted_date.between(start_date, end_date)).all()
    else:
        output = ctx.database_session.query(models.Control).join(models.ControlType).filter_by(name=con_type).all()
    logger.debug(f"Returned controls between dates: {[item.submitted_date for item in output]}")
    return output

def get_control_subtypes(ctx:Settings, type:str, mode:str) -> list[str]:
    """
    Get subtypes for a control analysis mode

    Args:
        ctx (Settings): settings object passed from gui
        type (str): control type name
        mode (str): analysis mode name

    Returns:
        list[str]: list of subtype names
    """    
    # Only the first control of type is necessary since they all share subtypes
    try:
        outs = get_all_controls_by_type(ctx=ctx, con_type=type)[0]
    except (TypeError, IndexError):
        return []
    # Get analysis mode data as dict
    jsoner = json.loads(getattr(outs, mode))
    logger.debug(f"JSON out: {jsoner}")
    try:
        genera = list(jsoner.keys())[0]
    except IndexError:
        return []
    subtypes = [item for item in jsoner[genera] if "_hashes" not in item and "_ratio" not in item]
    return subtypes

def get_all_controls(ctx:Settings) -> list[models.Control]:
    """
    Retrieve a list of all controls from the database

    Args:
        ctx (dict): settings passed down from the gui.

    Returns:
        list[models.Control]: list of all control objects
    """    
    return ctx.database_session.query(models.Control).all()

def lookup_submission_by_rsl_num(ctx:Settings, rsl_num:str) -> models.BasicSubmission:
    """
    Retrieve a submission from the database based on rsl plate number

    Args:
        ctx (Settings): settings object passed down from gui
        rsl_num (str): rsl plate number

    Returns:
        models.BasicSubmission: Submissions object retrieved from database
    """
    # return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num.startswith(rsl_num)).first()
    return ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num.startswith(rsl_num)).first()

def lookup_submissions_using_reagent(ctx:Settings, reagent:models.Reagent) -> list[models.BasicSubmission]:
    """
    Retrieves each submission using a specified reagent.

    Args:
        ctx (Settings): settings passed down from gui
        reagent (models.Reagent): reagent object in question

    Returns:
        list[models.BasicSubmission]: list of all submissions using specified reagent.
    """    
    # return ctx['database_session'].query(models.BasicSubmission).join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id).all()
    return ctx.database_session.query(models.BasicSubmission).join(reagents_submissions).filter(reagents_submissions.c.reagent_id==reagent.id).all()

def delete_submission_by_id(ctx:Settings, id:int) -> None:
    """
    Deletes a submission and its associated samples from the database.

    Args:
        ctx (Settings): settings object passed down from gui
        id (int): id of submission to be deleted.
    """    
    # In order to properly do this Im' going to have to delete all of the secondary table stuff as well.
    # Retrieve submission
    # sub = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()
    sub = ctx.database_session.query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()
    # Convert to dict for storing backup as a yml
    backup = sub.to_dict()
    try:
        # with open(Path(ctx['backup_path']).joinpath(f"{sub.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')}).yml"), "w") as f:
        with open(Path(ctx.backup_path).joinpath(f"{sub.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')}).yml"), "w") as f:
            yaml.dump(backup, f)
    except KeyError:
        pass
    # sub.reagents = []
    # for assoc in sub.submission_sample_associations:
    #     # if sample.rsl_plate == sub:
    #     if sub in sample.submissions:
    #         # ctx['database_session'].delete(sample)
        # ctx.database_session.delete(assoc)
    #     else:
    #         logger.warning(f"Not deleting sample {sample.ww_sample_full_id} because it belongs to another plate.")
    # ctx["database_session"].delete(sub)
    # ctx["database_session"].commit()
    
    ctx.database_session.delete(sub)
    try:
        ctx.database_session.commit()
    except (IntegrityError, OperationalError) as e:
        ctx.database_session.rollback()
        raise e

def lookup_ww_sample_by_rsl_sample_number(ctx:Settings, rsl_number:str) -> models.WastewaterSample:
    """
    Retrieves wastewater sample from database by rsl sample number

    Args:
        ctx (Settings): settings object passed down from gui
        rsl_number (str): sample number assigned by robotics lab

    Returns:
        models.WWSample: instance of wastewater sample
    """    
    # return ctx['database_session'].query(models.WWSample).filter(models.WWSample.rsl_number==rsl_number).first()
    return ctx.database_session.query(models.WastewaterSample).filter(models.WastewaterSample.rsl_number==rsl_number).first()

def lookup_ww_sample_by_ww_sample_num(ctx:Settings, sample_number:str) -> models.WastewaterSample:
    """
    Retrieves wastewater sample from database by ww sample number

    Args:
        ctx (Settings): settings object passed down from gui
        sample_number (str): sample number assigned by wastewater

    Returns:
        models.WWSample: instance of wastewater sample
    """    
    return ctx.database_session.query(models.WastewaterSample).filter(models.WastewaterSample.submitter_id==sample_number).first()

def lookup_ww_sample_by_sub_sample_rsl(ctx:Settings, sample_rsl:str, plate_rsl:str) -> models.WastewaterSample:
    """
    Retrieves a wastewater sample from the database by its rsl sample number and parent rsl plate number.
    This will likely replace simply looking up by the sample rsl above cine I need to control for repeats.

    Args:
        ctx (Settings): settings passed down from the gui
        sample_rsl (str): rsl number of the relevant sample
        plate_rsl (str): rsl number of the parent plate

    Returns:
        models.WWSample: Relevant wastewater object
    """    
    # return ctx['database_session'].query(models.WWSample).join(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==plate_rsl).filter(models.WWSample.rsl_number==sample_rsl).first()
    # return ctx.database_session.query(models.BasicSample).join(models.BasicSubmission).filter(models.BasicSubmission.rsl_plate_num==plate_rsl).filter(models.BasicSample.submitter_id==sample_rsl).first()
    return ctx.database_session.query(models.BasicSample).filter(models.BasicSample.submissions.any(models.BasicSubmission.rsl_plate_num==plate_rsl)).filter(models.WastewaterSample.rsl_number==sample_rsl).first()

def lookup_ww_sample_by_sub_sample_well(ctx:Settings, sample_rsl:str, well_num:str, plate_rsl:str) -> models.WastewaterSample:
    """
    Retrieves a wastewater sample from the database by its rsl sample number and parent rsl plate number.
    This will likely replace simply looking up by the sample rsl above cine I need to control for repeats.

    Args:
        ctx (Settings): settings object passed down from the gui
        sample_rsl (str): rsl number of the relevant sample
        well_num (str): well number of the relevant sample
        plate_rsl (str): rsl number of the parent plate

    Returns:
        models.WWSample: Relevant wastewater object
    """    
    # return ctx['database_session'].query(models.WWSample).join(models.BasicSubmission) \
    #     .filter(models.BasicSubmission.rsl_plate_num==plate_rsl) \
    #     .filter(models.WWSample.rsl_number==sample_rsl) \
    #     .filter(models.WWSample.well_number==well_num).first()
    return ctx.database_session.query(models.WastewaterSample).join(models.BasicSubmission) \
        .filter(models.BasicSubmission.rsl_plate_num==plate_rsl) \
        .filter(models.WastewaterSample.rsl_number==sample_rsl) \
        .filter(models.WastewaterSample.well_number==well_num).first()

def update_ww_sample(ctx:Settings, sample_obj:dict):
    """
    Retrieves wastewater sample by rsl number (sample_obj['sample']) and updates values from constructed dictionary

    Args:
        ctx (Settings): settings object passed down from gui
        sample_obj (dict): dictionary representing new values for database object
    """    
    # ww_samp = lookup_ww_sample_by_rsl_sample_number(ctx=ctx, rsl_number=sample_obj['sample'])
    logger.debug(f"Looking up {sample_obj['sample']} in plate {sample_obj['plate_rsl']}")
    # ww_samp = lookup_ww_sample_by_sub_sample_rsl(ctx=ctx, sample_rsl=sample_obj['sample'], plate_rsl=sample_obj['plate_rsl'])
    assoc = lookup_ww_association_by_plate_sample(ctx=ctx, rsl_plate_num=sample_obj['plate_rsl'], rsl_sample_num=sample_obj['sample'])
    # ww_samp = lookup_ww_sample_by_sub_sample_well(ctx=ctx, sample_rsl=sample_obj['sample'], well_num=sample_obj['well_num'], plate_rsl=sample_obj['plate_rsl'])
    if assoc != None:
        # del sample_obj['well_number']
        for key, value in sample_obj.items():
            # set attribute 'key' to 'value'
            try:
                check = getattr(assoc, key)
            except AttributeError:
                continue
            if check == None:
                logger.debug(f"Setting {key} to {value}")
                setattr(assoc, key, value)
    else:
        logger.error(f"Unable to find sample {sample_obj['sample']}")
        return
    # ctx['database_session'].add(ww_samp)
    # ctx["database_session"].commit()
    ctx.database_session.add(assoc)
    ctx.database_session.commit()

def lookup_discounts_by_org_and_kit(ctx:Settings, kit_id:int, lab_id:int) -> list:
    """
    Find discounts for kit for specified client

    Args:
        ctx (Settings): settings object passed down from gui
        kit_id (int): Id number of desired kit
        lab_id (int): Id number of desired client

    Returns:
        list: list of Discount objects
    """   
    # return ctx['database_session'].query(models.Discount).join(models.KitType).join(models.Organization).filter(and_(
    #     models.KitType.id==kit_id, 
    #     models.Organization.id==lab_id
    #     )).all()
    return ctx.database_session.query(models.Discount).join(models.KitType).join(models.Organization).filter(and_(
        models.KitType.id==kit_id, 
        models.Organization.id==lab_id
        )).all()

def hitpick_plate(submission:models.BasicSubmission, plate_number:int=0) -> list:
    """
    Creates a list of sample positions and statuses to be used by plate mapping and csv output to biomek software.
    DEPRECIATED: replaced by Submission.hitpick
    Args:
        submission (models.BasicSubmission): Input submission
        plate_number (int, optional): plate position in the series of selected plates. Defaults to 0.

    Returns:
        list: list of sample dictionaries.
    """    
    plate_dicto = []
    for sample in submission.samples:
        # have sample report back its info if it's positive, otherwise, None
        samp = sample.to_hitpick()
        if samp == None:
            continue
        else:
            logger.debug(f"Item name: {samp['name']}")
            # plate can handle 88 samples to leave column for controls
            # if len(dicto) < 88:
            this_sample = dict(
                plate_number = plate_number,
                sample_name = samp['name'],
                column = samp['column'],
                row = samp['row'],
                positive = samp['positive'],
                plate_name = submission.rsl_plate_num
            )
            # append to plate samples
            plate_dicto.append(this_sample)
            # append to all samples
    # image = make_plate_map(plate_dicto)
    return plate_dicto

def platemap_plate(submission:models.BasicSubmission) -> list:
    """
    Depreciated. Replaced by new functionality in hitpick_plate

    Args:
        submission (models.BasicSubmission): Input submission

    Returns:
        list: list of sample dictionaries
    """    
    plate_dicto = []
    for sample in submission.samples:
        # have sample report back its info if it's positive, otherwise, None
        
        try:
            samp = sample.to_platemap()
        except AttributeError:
            continue
        if samp == None:
            continue
        else:
            logger.debug(f"Item name: {samp['name']}")
            # plate can handle 88 samples to leave column for controls
            # if len(dicto) < 88:
            this_sample = dict(
                sample_name = samp['name'],
                column = samp['col'],
                row = samp['row'],
                plate_name = submission.rsl_plate_num
            )
            # append to plate samples
            plate_dicto.append(this_sample)
            # append to all samples
    # image = make_plate_map(plate_dicto)
    return plate_dicto

def lookup_reagent(ctx:Settings, reagent_lot:str, type_name:str|None=None) -> models.Reagent:
    """
    Query db for reagent based on lot number, with optional reagent type to enforce

    Args:
        ctx (Settings): settings passed down from gui
        reagent_lot (str): lot number to query
        type_name (str | None, optional): name of reagent type. Defaults to None.

    Returns:
        models.Reagent: looked up reagent
    """    
    if reagent_lot != None and type_name != None:
        # return ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).filter(models.Reagent.lot==reagent_lot).first()
        return ctx.database_session.query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).filter(models.Reagent.lot==reagent_lot).first()
    elif type_name == None:
        # return ctx['database_session'].query(models.Reagent).filter(models.Reagent.lot==reagent_lot).first()
        return ctx.database_session.query(models.Reagent).filter(models.Reagent.lot==reagent_lot).first()
    
def lookup_last_used_reagenttype_lot(ctx:Settings, type_name:str) -> models.Reagent:
    """
    Look up the last used reagent of the reagent type

    Args:
        ctx (Settings): Settings object passed down from gui
        type_name (str): Name of reagent type

    Returns:
        models.Reagent: Reagent object with last used lot.
    """    
    # rt = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==type_name).first()
    rt = ctx.database_session.query(models.ReagentType).filter(models.ReagentType.name==type_name).first()
    logger.debug(f"Reagent type looked up for {type_name}: {rt.__str__()}")
    try:
        return lookup_reagent(ctx=ctx, reagent_lot=rt.last_used, type_name=type_name)
    except AttributeError:
        return None

def check_kit_integrity(sub:models.BasicSubmission|models.KitType, reagenttypes:list|None=None) -> dict|None:
    """
    Ensures all reagents expected in kit are listed in Submission

    Args:
        sub (BasicSubmission | KitType): Object containing complete list of reagent types.
        reagenttypes (list | None, optional): List to check against complete list. Defaults to None.

    Returns:
        dict|None: Result object containing a message and any missing components.
    """    
    logger.debug(type(sub))
    # What type is sub?
    match sub:
        case models.BasicSubmission():
            # Get all required reagent types for this kit.
            # ext_kit_rtypes = [reagenttype.name for reagenttype in sub.extraction_kit.reagent_types if reagenttype.required == 1]
            ext_kit_rtypes = [item.name for item in sub.extraction_kit.get_reagents(required=True)]
            # Overwrite function parameter reagenttypes
            try:
                reagenttypes = [reagent.type.name for reagent in sub.reagents]
            except AttributeError as e:
                logger.error(f"Problem parsing reagents: {[f'{reagent.lot}, {reagent.type}' for reagent in sub.reagents]}")
        case models.KitType():
            # ext_kit_rtypes = [reagenttype.name for reagenttype in sub.reagent_types if reagenttype.required == 1]
            ext_kit_rtypes = [item.name for item in sub.get_reagents(required=True)]
        case _:
            raise ValueError(f"There was no match for the integrity object.\n\nCheck to make sure they are imported from the same place because it matters.")
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    logger.debug(f"Submission reagents: {reagenttypes}")
    # check if lists are equal
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    # what reagent types are in both lists?
    missing = list(set(ext_kit_rtypes).difference(reagenttypes))
    logger.debug(f"Missing reagents types: {missing}")
    # if lists are equal return no problem
    if len(missing)==0:
        result = None
    else:
        result = {'message' : f"The submission you are importing is missing some reagents expected by the kit.\n\nIt looks like you are missing: {[item.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.\n\nThe program will populate lists using existing reagents.\n\nPlease make sure you check the lots carefully!", 'missing': missing}
    return result

def lookup_sample_by_submitter_id(ctx:Settings, submitter_id:str) -> models.BasicSample:
    """
    _summary_

    Args:
        ctx (Settings): _description_
        submitter_id (str): _description_

    Returns:
        BasicSample: _description_
    """    
    return ctx.database_session.query(models.BasicSample).filter(models.BasicSample.submitter_id==submitter_id).first()

def get_all_submission_types(ctx:Settings) -> List[str]:
    """
    _summary_

    Args:
        ctx (Settings): _description_

    Returns:
        List[str]: _description_
    """    
    kits = ctx.database_session.query(KitType).all()
    uses = [list(item.used_for.keys()) for item in kits]
    flat_list = [item for sublist in uses for item in sublist]
    return list(set(flat_list)).sort()

def get_reagents_in_extkit(ctx:Settings, kit_name:str) -> List[str]:
    """
    _summary_
    DEPRECIATED, use kit.get_reagents() instead

    Args:
        ctx (Settings): _description_
        kit_name (str): _description_

    Returns:
        List[str]: _description_
    """    
    kit = lookup_kittype_by_name(ctx=ctx, name=kit_name)
    return kit.get_reagents(required=False)

def lookup_ww_association_by_plate_sample(ctx:Settings, rsl_plate_num:str, rsl_sample_num:str) -> models.SubmissionSampleAssociation:
    """
    _summary_

    Args:
        ctx (Settings): _description_
        rsl_plate_num (str): _description_
        sample_submitter_id (_type_): _description_

    Returns:
        models.SubmissionSampleAssociation: _description_
    """    
    return ctx.database_session.query(models.SubmissionSampleAssociation)\
                .join(models.BasicSubmission)\
                .join(models.WastewaterSample)\
                .filter(models.BasicSubmission.rsl_plate_num==rsl_plate_num)\
                .filter(models.WastewaterSample.rsl_number==rsl_sample_num)\
                .first()

def lookup_all_reagent_names_by_role(ctx:Settings, role_name:str) -> List[str]:
    """
    _summary_

    Args:
        ctx (Settings): _description_
        role_name (str): _description_

    Returns:
        List[str]: _description_
    """    
    role = lookup_reagenttype_by_name(ctx=ctx, rt_name=role_name)
    try:
        return [reagent.name for reagent in role.instances]
    except AttributeError:
        return []