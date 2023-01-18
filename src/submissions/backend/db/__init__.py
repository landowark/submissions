from . import models
import pandas as pd
# from sqlite3 import IntegrityError
from sqlalchemy.exc import IntegrityError
import logging
import datetime
from sqlalchemy import and_
import uuid
import base64

logger = logging.getLogger(__name__)

def get_kits_by_use( ctx:dict, kittype_str:str|None) -> list:
    pass
    # ctx dict should contain the database session


def store_submission(ctx:dict, base_submission:models.BasicSubmission) -> None:
    ctx['database_session'].add(base_submission)
    try:
        ctx['database_session'].commit()
    except IntegrityError:
        ctx['database_session'].rollback()
        return {"message":"This plate number already exists, so we can't add it."}
    return None


def store_reagent(ctx:dict, reagent:models.Reagent) -> None:
    print(reagent.__dict__)
    ctx['database_session'].add(reagent)
    ctx['database_session'].commit()


def construct_submission_info(ctx:dict, info_dict:dict) -> models.BasicSubmission:
    query = info_dict['submission_type'].replace(" ", "")
    model = getattr(models, query)
    info_dict['submission_type'] = info_dict['submission_type'].replace(" ", "_").lower()
    instance = model()
    for item in info_dict:
        print(f"Setting {item} to {info_dict[item]}")
        match item:
            case "extraction_kit":
                q_str = info_dict[item]
                print(f"Looking up kit {q_str}")
                field_value = lookup_kittype_by_name(ctx=ctx, name=q_str)
                print(f"Got {field_value} for kit {q_str}")
            case "submitting_lab":
                q_str = info_dict[item].replace(" ", "_").lower()
                print(f"looking up organization: {q_str}")
                field_value = lookup_org_by_name(ctx=ctx, name=q_str)
                print(f"Got {field_value} for organization {q_str}")
            case "submitter_plate_num":
                # Because of unique constraint, the submitter plate number cannot be None, so...
                if info_dict[item] == None:
                    info_dict[item] = uuid.uuid4().hex.upper()
            case _:
                field_value = info_dict[item]
        try:
            setattr(instance, item, field_value)
        except AttributeError:
            print(f"Could not set attribute: {item} to {info_dict[item]}")
            continue
    return instance
    # looked_up = []
    # for reagent in reagents:
    #     my_reagent = lookup_reagent(reagent)
    #     print(my_reagent)
    #     looked_up.append(my_reagent)
    # print(looked_up)
    # instance.reagents = looked_up
    # ctx['database_session'].add(instance)
    # ctx['database_session'].commit()

def construct_reagent(ctx:dict, info_dict:dict) -> models.Reagent:
    reagent = models.Reagent()
    for item in info_dict:
        print(f"Reagent info item: {item}")
        match item:
            case "lot":
                reagent.lot = info_dict[item].upper()
            case "expiry":
                reagent.expiry = info_dict[item]
            case "type":
                reagent.type = lookup_reagenttype_by_name(ctx=ctx, rt_name=info_dict[item].replace(" ", "_").lower())
    try:
        reagent.expiry = reagent.expiry + reagent.type.eol_ext
    except TypeError as e:
        print(f"WE got a type error: {e}.")
    except AttributeError:
        pass
    return reagent



def lookup_reagent(ctx:dict, reagent_lot:str):
    lookedup = ctx['database_session'].query(models.Reagent).filter(models.Reagent.lot==reagent_lot).first()
    return lookedup

def get_all_reagenttype_names(ctx:dict) -> list[str]:
    lookedup = [item.__str__() for item in ctx['database_session'].query(models.ReagentType).all()]
    return lookedup

def lookup_reagenttype_by_name(ctx:dict, rt_name:str) -> models.ReagentType:
    print(f"Looking up ReagentType by name: {rt_name}")
    lookedup = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==rt_name).first()
    print(f"Found ReagentType: {lookedup}")
    return lookedup


def lookup_kittype_by_use(ctx:dict, used_by:str) -> list[models.KitType]:
    # return [item for item in 
    return ctx['database_session'].query(models.KitType).filter(models.KitType.used_for.contains(used_by))

def lookup_kittype_by_name(ctx:dict, name:str) -> models.KitType:
    print(f"Querying kittype: {name}")
    return ctx['database_session'].query(models.KitType).filter(models.KitType.name==name).first()


def lookup_regent_by_type_name(ctx:dict, type_name:str) -> list[models.ReagentType]:
    # return [item for item in ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).all()]
    return ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name==type_name).all()


def lookup_regent_by_type_name_and_kit_name(ctx:dict, type_name:str, kit_name:str) -> list[models.Reagent]:
    # Hang on, this is going to be a long one.
    by_type = ctx['database_session'].query(models.Reagent).join(models.Reagent.type, aliased=True).filter(models.ReagentType.name.endswith(type_name))
    add_in = by_type.join(models.ReagentType.kits).filter(models.KitType.name==kit_name)
    return add_in


def lookup_all_submissions_by_type(ctx:dict, type:str|None=None):
    if type == None:
        subs = ctx['database_session'].query(models.BasicSubmission).all()
    else:
        subs = ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.submission_type==type).all()
    return subs

def lookup_all_orgs(ctx:dict) -> list[models.Organization]:
    return ctx['database_session'].query(models.Organization).all()

def lookup_org_by_name(ctx:dict, name:str|None) -> models.Organization:
    print(f"Querying organization: {name}")
    return ctx['database_session'].query(models.Organization).filter(models.Organization.name==name).first()

def submissions_to_df(ctx:dict, type:str|None=None):
    print(f"Type: {type}")
    subs = [item.to_dict() for item in lookup_all_submissions_by_type(ctx=ctx, type=type)]
    df = pd.DataFrame.from_records(subs)
    return df
     
    
def lookup_submission_by_id(ctx:dict, id:int) -> models.BasicSubmission:
    return ctx['database_session'].query(models.BasicSubmission).filter(models.BasicSubmission.id==id).first()


def create_submission_details(ctx:dict, sub_id:int) -> dict:
    pass


def lookup_submissions_by_date_range(ctx:dict, start_date:datetime.date, end_date:datetime.date) -> list[models.BasicSubmission]:
    return ctx['database_session'].query(models.BasicSubmission).filter(and_(models.BasicSubmission.submitted_date > start_date, models.BasicSubmission.submitted_date < end_date)).all()


def get_all_Control_Types_names(ctx:dict) -> list[models.ControlType]:
    """
    Grabs all control type names from db.

    Args:
        settings (dict): settings passed down from click. Defaults to {}.

    Returns:
        list: names list
    """    
    conTypes = ctx['database_session'].query(models.ControlType).all()
    conTypes = [conType.name for conType in conTypes]
    logger.debug(f"Control Types: {conTypes}")
    return conTypes


def create_kit_from_yaml(ctx:dict, exp:dict) -> None:
    """
    Create and store a new kit in the database based on a .yml file

    Args:
        ctx (dict): Context dictionary passed down from frontend
        exp (dict): Experiment dictionary created from yaml file
    """    
    if base64.b64encode(exp['password']) != b'cnNsX3N1Ym1pNTVpb25z':
        print(f"Not the correct password.")
        return
    for type in exp:
        if type == "password":
            continue
        for kt in exp[type]['kits']:
            kit = models.KitType(name=kt, used_for=[type.replace("_", " ").title()], cost_per_run=exp[type]["kits"][kt]["cost"])
            for r in exp[type]['kits'][kt]['reagenttypes']:
                look_up = ctx['database_session'].query(models.ReagentType).filter(models.ReagentType.name==r).first()
                if look_up == None:
                    rt = models.ReagentType(name=r.replace(" ", "_").lower(), eol_ext=datetime.timedelta(30*exp[type]['kits'][kt]['reagenttypes'][r]['eol_ext']), kits=[kit])
                else:
                    rt = look_up
                    rt.kits.append(kit)
                ctx['database_session'].add(rt)
                print(rt.__dict__)
            print(kit.__dict__)
        ctx['database_session'].add(kit)
    ctx['database_session'].commit()


def lookup_all_sample_types(ctx:dict) -> list[str]:
    uses = [item.used_for for item in ctx['database_session'].query(models.KitType).all()]
    uses = list(set([item for sublist in uses for item in sublist]))
    return uses