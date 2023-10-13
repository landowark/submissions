'''
Contains convenience functions for using database
'''
from tools import Settings
from .lookups import *
import pandas as pd
import json
from pathlib import Path
import yaml
from .. import models
from . import store_object
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from pprint import pformat

def submissions_to_df(ctx:Settings, submission_type:str|None=None, limit:int=0) -> pd.DataFrame:
    """
    Convert submissions looked up by type to dataframe

    Args:
        ctx (Settings): settings object passed by gui
        submission_type (str | None, optional): submission type (should be string in D3 of excel sheet) Defaults to None.
        limit (int): Maximum number of submissions to return. Defaults to 0.

    Returns:
        pd.DataFrame: dataframe constructed from retrieved submissions
    """    
    logger.debug(f"Querying Type: {submission_type}")
    logger.debug(f"Using limit: {limit}")
    # use lookup function to create list of dicts
    subs = [item.to_dict() for item in lookup_submissions(ctx=ctx, submission_type=submission_type, limit=limit)]
    logger.debug(f"Got {len(subs)} results.")
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
    # NOTE: Moved to submissions_to_df function
    try:
        del df['samples']
    except KeyError:
        pass
    try:
        del df['reagents']
    except KeyError:
        pass
    try:
        del df['comments']
    except KeyError:
        pass
    return df

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
        outs = lookup_controls(ctx=ctx, control_type=type, limit=1)
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

def update_last_used(ctx:Settings, reagent:models.Reagent, kit:models.KitType):
    """
    Updates the 'last_used' field in kittypes/reagenttypes

    Args:
        ctx (Settings): settings object passed down from gui
        reagent (models.Reagent): reagent to be used for update
        kit (models.KitType): kit to be used for lookup
    """    
    # rt = list(set(reagent.type).intersection(kit.reagent_types))[0]
    rt = lookup_reagent_types(ctx=ctx, kit_type=kit, reagent=reagent)
    if rt != None:
        assoc = lookup_reagenttype_kittype_association(ctx=ctx, kit_type=kit, reagent_type=rt)
        if assoc != None:
            if assoc.last_used != reagent.lot:
                logger.debug(f"Updating {assoc} last used to {reagent.lot}")
                assoc.last_used = reagent.lot
                # ctx.database_session.merge(assoc)
                # ctx.database_session.commit()
                result = store_object(ctx=ctx, object=assoc)
                return result  
    return dict(message=f"Updating last used {rt} was not performed.") 

def delete_submission(ctx:Settings, id:int) -> dict|None:
    """
    Deletes a submission and its associated samples from the database.

    Args:
        ctx (Settings): settings object passed down from gui
        id (int): id of submission to be deleted.
    """    
    # In order to properly do this Im' going to have to delete all of the secondary table stuff as well.
    # Retrieve submission
    sub = lookup_submissions(ctx=ctx, id=id)
    # Convert to dict for storing backup as a yml
    backup = sub.to_dict()
    try:
        with open(Path(ctx.backup_path).joinpath(f"{sub.rsl_plate_num}-backup({date.today().strftime('%Y%m%d')}).yml"), "w") as f:
            yaml.dump(backup, f)
    except KeyError:
        pass
    ctx.database_session.delete(sub)
    try:
        ctx.database_session.commit()
    except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
        ctx.database_session.rollback()
        raise e
    return None
    
def update_ww_sample(ctx:Settings, sample_obj:dict) -> dict|None:
    """
    Retrieves wastewater sample by rsl number (sample_obj['sample']) and updates values from constructed dictionary

    Args:
        ctx (Settings): settings object passed down from gui
        sample_obj (dict): dictionary representing new values for database object
    """    
    logger.debug(f"dictionary to use for update: {pformat(sample_obj)}")
    logger.debug(f"Looking up {sample_obj['sample']} in plate {sample_obj['plate_rsl']}")
    assoc = lookup_submission_sample_association(ctx=ctx, submission=sample_obj['plate_rsl'], sample=sample_obj['sample'])
    if assoc != None:
        for key, value in sample_obj.items():
            # set attribute 'key' to 'value'
            try:
                check = getattr(assoc, key)
            except AttributeError as e:
                logger.error(f"Item doesn't have field {key} due to {e}")
                continue
            if check != value:
                logger.debug(f"Setting association key: {key} to {value}")
                try:
                    setattr(assoc, key, value)
                except AttributeError as e:
                    logger.error(f"Can't set field {key} to {value} due to {e}")
                    continue
    else:
        logger.error(f"Unable to find sample {sample_obj['sample']}")
        return
    result = store_object(ctx=ctx, object=assoc)
    return result

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
    reagenttypes = []
    match sub:
        case models.BasicSubmission():
            # Get all required reagent types for this kit.
            ext_kit_rtypes = [item.name for item in sub.extraction_kit.get_reagents(required=True, submission_type=sub.submission_type_name)]
            # Overwrite function parameter reagenttypes
            for reagent in sub.reagents:
                try:
                    rt = list(set(reagent.type).intersection(sub.extraction_kit.reagent_types))[0].name
                    logger.debug(f"Got reagent type: {rt}")
                    reagenttypes.append(rt)
                except AttributeError as e:
                    logger.error(f"Problem parsing reagents: {[f'{reagent.lot}, {reagent.type}' for reagent in sub.reagents]}")
                    reagenttypes.append(reagent.type[0].name)
        case models.KitType():
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

def update_subsampassoc_with_pcr(ctx:Settings, submission:models.BasicSubmission, sample:models.BasicSample, input_dict:dict) -> dict|None:
    """
    Inserts PCR results into wastewater submission/sample association

    Args:
        ctx (Settings): settings object passed down from gui
        submission (models.BasicSubmission): Submission object
        sample (models.BasicSample): Sample object
        input_dict (dict): dictionary with info to be updated.

    Returns:
        dict|None: result object
    """    
    assoc = lookup_submission_sample_association(ctx, submission=submission, sample=sample)
    for k,v in input_dict.items():
        try:
            setattr(assoc, k, v)
        except AttributeError:
            logger.error(f"Can't set {k} to {v}")
    result = store_object(ctx=ctx, object=assoc)
    return result

def get_polymorphic_subclass(base:object, polymorphic_identity:str|None=None):
    """
    Retrieves any subclasses of given base class whose polymorphic identity matches the string input.

    Args:
        base (object): Base (parent) class
        polymorphic_identity (str | None): Name of subclass of interest. (Defaults to None)

    Returns:
        _type_: Subclass, or parent class on 
    """    
    if isinstance(polymorphic_identity, dict):
        polymorphic_identity = polymorphic_identity['value']
    if polymorphic_identity == None:
        return base
    else:
        try:
            return [item for item in base.__subclasses__() if item.__mapper_args__['polymorphic_identity']==polymorphic_identity][0]
        except Exception as e:
            logger.error(f"Could not get polymorph {polymorphic_identity} of {base} due to {e}")
            return base

