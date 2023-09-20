'''
contains parser object for pulling values from client generated submission sheets.
'''
from getpass import getuser
import pprint
from typing import List
import pandas as pd
from pathlib import Path
from backend.db import lookup_sample_by_submitter_id, get_reagents_in_extkit, lookup_kittype_by_name, lookup_submissiontype_by_name, models
from backend.pydant import PydSubmission, PydReagent
import logging
from collections import OrderedDict
import re
import numpy as np
from datetime import date
from dateutil.parser import parse, ParserError
from tools import check_not_nan, RSLNamer, convert_nans_to_nones, Settings, convert_well_to_row_column
from frontend.custom_widgets.pop_ups import SubmissionTypeSelector, KitSelector

logger = logging.getLogger(f"submissions.{__name__}")

row_keys = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)

class SheetParser(object):
    """
    object to pull and contain data from excel file
    """
    def __init__(self, ctx:Settings, filepath:Path|None = None):
        """
        Args:
            ctx (Settings): Settings object passed down from gui
            filepath (Path | None, optional): file path to excel sheet. Defaults to None.
        """        
        self.ctx = ctx
        logger.debug(f"Parsing {filepath.__str__()}")
        if filepath == None:
            logger.error(f"No filepath given.")
            self.xl = None
        else:
            self.filepath = filepath
            # Open excel file
            try:
                self.xl = pd.ExcelFile(filepath)
            except ValueError as e:
                logger.error(f"Incorrect value: {e}")
                self.xl = None
        self.sub = OrderedDict()
        # make decision about type of sample we have
        self.sub['submission_type'] = self.type_decider()
        # # grab the info map from the submission type in database
        self.parse_info()
        self.import_kit_validation_check()
        self.parse_reagents()
        self.import_reagent_validation_check()
        self.parse_samples()
       

    def type_decider(self) -> str:
        """
        makes decisions about submission type based on structure of excel file

        Returns:
            str: submission type name
        """        
        # Check metadata for category, return first category
        if self.xl.book.properties.category != None:
            logger.debug("Using file properties to find type...")
            categories = [item.strip().replace("_", " ").title() for item in self.xl.book.properties.category.split(";")]
            return dict(value=categories[0], parsed=False)
        else:
            # This code is going to be depreciated once there is full adoption of the client sheets
            # with updated metadata... but how will it work for Artic?
            logger.debug("Using excel map to find type...")
            try:
                for type in self.ctx.submission_types:
                    # This gets the *first* submission type that matches the sheet names in the workbook 
                    if self.xl.sheet_names == self.ctx.submission_types[type]['excel_map']:
                        return dict(value=type.title(), parsed=True)
                return "Unknown"
            except Exception as e:
                logger.warning(f"We were unable to parse the submission type due to: {e}")
                # return "Unknown"
                dlg = SubmissionTypeSelector(ctx=self.ctx, title="Select Submission Type", message="We were unable to find the submission type from the excel metadata. Please select from below.")
                if dlg.exec():
                    return dict(value=dlg.getValues(), parsed=False)
                else:
                    logger.warning(f"Last attempt at getting submission was rejected.")
                    raise ValueError("Submission Type needed.")
                
    def parse_info(self):
        """
        Pulls basic information from the excel sheet
        """        
        info = InfoParser(ctx=self.ctx, xl=self.xl, submission_type=self.sub['submission_type']['value']).parse_info()
        parser_query = f"parse_{self.sub['submission_type']['value'].replace(' ', '_').lower()}"
        try:
            custom_parser = getattr(self, parser_query)
            info = custom_parser(info)
        except AttributeError:
            logger.error(f"Couldn't find submission parser: {parser_query}")
        for k,v in info.items():
            match k:
                case "sample":
                    pass
                case _:
                    self.sub[k] = v
        logger.debug(f"Parser.sub after info scrape: {pprint.pformat(self.sub)}")

    def parse_reagents(self):
        """
        Pulls reagent info from the excel sheet
        """        
        self.sub['reagents'] = ReagentParser(ctx=self.ctx, xl=self.xl, submission_type=self.sub['submission_type'], extraction_kit=self.sub['extraction_kit']).parse_reagents()

    def parse_samples(self):
        """
        Pulls sample info from the excel sheet
        """        
        self.sample_result, self.sub['samples'] = SampleParser(ctx=self.ctx, xl=self.xl, submission_type=self.sub['submission_type']['value']).parse_samples()

    def parse_bacterial_culture(self, input_dict) -> dict:
        """
        Update submission dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        return input_dict
        
    def parse_wastewater(self, input_dict) -> dict:
        """
        Update submission dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        return input_dict

    def parse_wastewater_artic(self, input_dict:dict) -> dict:
        """
        Update submission dictionary with type specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        return input_dict


    def import_kit_validation_check(self):
        """
        Enforce that the parser has an extraction kit

        Args:
            ctx (Settings): Settings obj passed down from gui
            parser_sub (dict): The parser dictionary before going to pydantic

        Returns:
            List[PydReagent]: List of reagents
        """    
        if not check_not_nan(self.sub['extraction_kit']['value']):
            dlg = KitSelector(ctx=self.ctx, title="Kit Needed", message="At minimum a kit is needed. Please select one.")
            if dlg.exec():
                self.sub['extraction_kit'] = dict(value=dlg.getValues(), parsed=False)
            else:
                raise ValueError("Extraction kit needed.")
        else:
            if isinstance(self.sub['extraction_kit'], str):
                self.sub['extraction_kit'] = dict(value=self.sub['extraction_kit'], parsed=False)

    def import_reagent_validation_check(self):
        """
        Enforce that only allowed reagents get into the Pydantic Model
        """          
        allowed_reagents = [item.name for item in get_reagents_in_extkit(ctx=self.ctx, kit_name=self.sub['extraction_kit']['value'])]
        logger.debug(f"List of reagents for comparison with allowed_reagents: {pprint.pformat(self.sub['reagents'])}")
        self.sub['reagents'] = [reagent for reagent in self.sub['reagents'] if reagent['value'].type in allowed_reagents]
        
    def to_pydantic(self) -> PydSubmission:
        """
        Generates a pydantic model of scraped data for validation

        Returns:
            PydSubmission: output pydantic model
        """       
        logger.debug(f"Submission dictionary coming into 'to_pydantic':\n{pprint.pformat(self.sub)}")
        psm = PydSubmission(ctx=self.ctx, filepath=self.filepath, **self.sub)
        delattr(psm, "filepath")
        return psm
    
class InfoParser(object):

    def __init__(self, ctx:Settings, xl:pd.ExcelFile, submission_type:str):
        self.ctx = ctx
        self.map = self.fetch_submission_info_map(submission_type=submission_type)
        self.xl = xl
        logger.debug(f"Info map for InfoParser: {pprint.pformat(self.map)}")

    def fetch_submission_info_map(self, submission_type:str|dict) -> dict:
        """
        Gets location of basic info from the submission_type object in the database.

        Args:
            submission_type (str|dict): name of the submission type or parsed object with value=submission_type

        Returns:
            dict: Location map of all info for this submission type
        """        
        if isinstance(submission_type, str):
            submission_type = dict(value=submission_type, parsed=False)
        logger.debug(f"Looking up submission type: {submission_type['value']}")
        submission_type = lookup_submissiontype_by_name(ctx=self.ctx, type_name=submission_type['value'])
        info_map = submission_type.info_map
        return info_map

    def parse_info(self) -> dict:
        """
        Pulls basic info from the excel sheet.

        Returns:
            dict: key:value of basic info
        """        
        dicto = {}
        for sheet in self.xl.sheet_names:
            df = self.xl.parse(sheet, header=None)
            relevant = {}
            for k, v in self.map.items():
                if isinstance(v, str):
                    dicto[k] = dict(value=v, parsed=True)
                    continue
                if k == "samples":
                    continue
                if sheet in self.map[k]['sheets']:
                    relevant[k] = v
            logger.debug(f"relevant map for {sheet}: {pprint.pformat(relevant)}")
            if relevant == {}:
                continue
            for item in relevant:
                value = df.iat[relevant[item]['row']-1, relevant[item]['column']-1]
                logger.debug(f"Setting {item} on {sheet} to {value}")
                if check_not_nan(value):
                    if value != "None":
                        try:
                            dicto[item] = dict(value=value, parsed=True)
                        except (KeyError, IndexError):
                            continue
                    else:
                        try:
                            dicto[item] = dict(value=value, parsed=False)
                        except (KeyError, IndexError):
                            continue
                else:
                    dicto[item] = dict(value=convert_nans_to_nones(value), parsed=False)
        return dicto
                
class ReagentParser(object):

    def __init__(self, ctx:Settings, xl:pd.ExcelFile, submission_type:str, extraction_kit:str):
        self.ctx = ctx
        self.map = self.fetch_kit_info_map(extraction_kit=extraction_kit, submission_type=submission_type)
        self.xl = xl

    def fetch_kit_info_map(self, extraction_kit:dict, submission_type:str):
        kit = lookup_kittype_by_name(ctx=self.ctx, name=extraction_kit['value'])
        if isinstance(submission_type, dict):
            submission_type = submission_type['value']
        reagent_map = kit.construct_xl_map_for_use(submission_type.title())
        del reagent_map['info']
        return reagent_map
    
    def parse_reagents(self) -> list:
        listo = []
        for sheet in self.xl.sheet_names:
            df = self.xl.parse(sheet, header=None, dtype=object)
            relevant = {k.strip():v for k,v in self.map.items() if sheet in self.map[k]['sheet']}
            logger.debug(f"relevant map for {sheet}: {pprint.pformat(relevant)}")
            if relevant == {}:
                continue
            for item in relevant:
                logger.debug(f"Attempting to scrape: {item}")
                try:
                    name = df.iat[relevant[item]['name']['row']-1, relevant[item]['name']['column']-1]
                    lot = df.iat[relevant[item]['lot']['row']-1, relevant[item]['lot']['column']-1]
                    expiry = df.iat[relevant[item]['expiry']['row']-1, relevant[item]['expiry']['column']-1]
                except (KeyError, IndexError):
                    listo.append(dict(value=PydReagent(type=item.strip(), lot=None, exp=None, name=None), parsed=False))
                    continue
                if check_not_nan(lot):
                    parsed = True
                else:
                    parsed = False
                logger.debug(f"Got lot for {item}-{name}: {lot} as {type(lot)}")
                lot = str(lot)
                listo.append(dict(value=PydReagent(type=item.strip(), lot=lot, exp=expiry, name=name), parsed=parsed))
        return listo


class SampleParser(object):
    """
    object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, ctx:Settings, xl:pd.ExcelFile, submission_type:str) -> None:
        """
        convert sample sub-dataframe to dictionary of records

        Args:
            ctx (Settings): settings object passed down from gui
            df (pd.DataFrame): input sample dataframe
            elution_map (pd.DataFrame | None, optional): optional map of elution plate. Defaults to None.
        """        
        self.samples = []
        self.ctx = ctx
        self.xl = xl
        self.submission_type = submission_type
        sample_info_map = self.fetch_sample_info_map(submission_type=submission_type)
        self.plate_map = self.construct_plate_map(plate_map_location=sample_info_map['plate_map'])
        self.lookup_table = self.construct_lookup_table(lookup_table_location=sample_info_map['lookup_table'])
        if "plates" in sample_info_map:
            self.plates = sample_info_map['plates']
        self.excel_to_db_map = sample_info_map['xl_db_translation']
        self.create_basic_dictionaries_from_plate_map()
        if isinstance(self.lookup_table, pd.DataFrame):
            self.parse_lookup_table()
        
    def fetch_sample_info_map(self, submission_type:dict) -> dict:
        logger.debug(f"Looking up submission type: {submission_type}")
        submission_type = lookup_submissiontype_by_name(ctx=self.ctx, type_name=submission_type)
        logger.debug(f"info_map: {pprint.pformat(submission_type.info_map)}")
        sample_info_map = submission_type.info_map['samples']
        return sample_info_map

    def construct_plate_map(self, plate_map_location:dict) -> pd.DataFrame:
        df = self.xl.parse(plate_map_location['sheet'], header=None, dtype=object)
        df = df.iloc[plate_map_location['start_row']-1:plate_map_location['end_row'], plate_map_location['start_column']-1:plate_map_location['end_column']]
        # logger.debug(f"Input dataframe for plate map: {df}")
        df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
        df = df.set_index(df.columns[0])
        # logger.debug(f"Output dataframe for plate map: {df}")
        return df
    
    def construct_lookup_table(self, lookup_table_location) -> pd.DataFrame:
        try:
            df = self.xl.parse(lookup_table_location['sheet'], header=None, dtype=object)
        except KeyError:
            return None
        df = df.iloc[lookup_table_location['start_row']-1:lookup_table_location['end_row']]
        df = pd.DataFrame(df.values[1:], columns=df.iloc[0])
        df = df.reset_index(drop=True)
        # logger.debug(f"Dataframe for lookup table: {df}")
        return df
    
    def create_basic_dictionaries_from_plate_map(self):
        invalids = [0, "0", "EMPTY"]
        new_df = self.plate_map.dropna(axis=1, how='all')
        columns = new_df.columns.tolist()
        for _, iii in new_df.iterrows():
            for c in columns:
                # logger.debug(f"Checking sample {iii[c]}")
                if check_not_nan(iii[c]):
                    if iii[c] in invalids:
                        logger.debug(f"Invalid sample name: {iii[c]}, skipping.")
                        continue
                    id = iii[c]
                    logger.debug(f"Adding sample {iii[c]}")
                    try:
                        c = self.plate_map.columns.get_loc(c) + 1
                    except Exception as e:
                        logger.error(f"Unable to get column index of {c} due to {e}")
                    self.samples.append(dict(submitter_id=id, row=row_keys[iii._name], column=c))
    
    def parse_lookup_table(self):
        def determine_if_date(input_str) -> str|date:
            # logger.debug(f"Looks like we have a str: {input_str}")
            regex = re.compile(r"^\d{4}-?\d{2}-?\d{2}")
            if bool(regex.search(input_str)):
                logger.warning(f"{input_str} is a date!")
                try:
                    return parse(input_str)
                except ParserError:
                    return None
            else:
                return input_str
        for sample in self.samples:
            addition = self.lookup_table[self.lookup_table.isin([sample['submitter_id']]).any(axis=1)].squeeze().to_dict()
            logger.debug(f"Lookuptable info: {addition}")
            for k,v in addition.items():
                # logger.debug(f"Checking {k} in lookup table.")
                if check_not_nan(k) and isinstance(k, str):
                    if k.lower() not in sample:
                        k = k.replace(" ", "_").replace("#","num").lower()
                        # logger.debug(f"Adding {type(v)} - {k}, {v} to the lookuptable output dict")
                        match v:
                            case pd.Timestamp():
                                sample[k] = v.date()
                            case str():
                                sample[k] = determine_if_date(v)
                            case _:
                                sample[k] = v
            logger.debug(f"Output sample dict: {sample}")

    def parse_samples(self, generate:bool=True) -> List[dict]:
        result = None
        new_samples = []
        for ii, sample in enumerate(self.samples):
            # logger.debug(f"\n\n{new_samples}\n\n")
            try:
                if sample['submitter_id'] in [check_sample['sample'].submitter_id for check_sample in new_samples]:
                    sample['submitter_id'] = f"{sample['submitter_id']}-{ii}"
            except KeyError as e:
                logger.error(f"Sample obj: {sample}, error: {e}")
            translated_dict = {}
            for k, v in sample.items():
                match v:
                    case dict():
                        v = None
                    case float():
                        v = convert_nans_to_nones(v)
                    case _:
                        v = v
                try:
                    translated_dict[self.excel_to_db_map[k]] = convert_nans_to_nones(v)
                except KeyError:
                    translated_dict[k] = convert_nans_to_nones(v)
            translated_dict['sample_type'] = f"{self.submission_type} Sample"
            parser_query = f"parse_{translated_dict['sample_type'].replace(' ', '_').lower()}"
            # logger.debug(f"New sample dictionary going into object creation:\n{translated_dict}")
            try:
                custom_parser = getattr(self, parser_query)
                translated_dict = custom_parser(translated_dict)
            except AttributeError:
                logger.error(f"Couldn't get custom parser: {parser_query}")
            if generate:
                new_samples.append(self.generate_sample_object(translated_dict))
            else:
                new_samples.append(translated_dict)
        return result, new_samples

    def generate_sample_object(self, input_dict) -> models.BasicSample:
        query = input_dict['sample_type'].replace(" ", "")
        try:
            database_obj = getattr(models, query)
        except AttributeError as e:
            logger.error(f"Could not find the model {query}. Using generic.")
            database_obj = models.BasicSample
        logger.debug(f"Searching database for {input_dict['submitter_id']}...")
        instance = lookup_sample_by_submitter_id(ctx=self.ctx, submitter_id=input_dict['submitter_id'])
        if instance == None:
            logger.debug(f"Couldn't find sample {input_dict['submitter_id']}. Creating new sample.")
            instance = database_obj()
            for k,v in input_dict.items():
                try:
                    # setattr(instance, k, v)
                    instance.set_attribute(k, v)
                except Exception as e:
                    logger.error(f"Failed to set {k} due to {type(e).__name__}: {e}")
        else:
            logger.debug(f"Sample {instance.submitter_id} already exists, will run update.")
        return dict(sample=instance, row=input_dict['row'], column=input_dict['column'])


    def parse_bacterial_culture_sample(self, input_dict:dict) -> dict:
        """
        Update sample dictionary with bacterial culture specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        logger.debug("Called bacterial culture sample parser")
        return input_dict

    def parse_wastewater_sample(self, input_dict:dict) -> dict:
        """
        Update sample dictionary with wastewater specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        logger.debug(f"Called wastewater sample parser")
        return input_dict
    
    def parse_wastewater_artic_sample(self, input_dict:dict) -> dict:
        """
        Update sample dictionary with artic specific information

        Args:
            input_dict (dict): Input sample dictionary

        Returns:
            dict: Updated sample dictionary
        """        
        logger.debug("Called wastewater artic sample parser")
        input_dict['sample_type'] = "Wastewater Sample"
        # Because generate_sample_object needs the submitter_id and the artic has the "({origin well})"
        # at the end, this has to be done here. No moving to sqlalchemy object :(
        input_dict['submitter_id'] = re.sub(r"\s\(.+\)$", "", str(input_dict['submitter_id'])).strip()
        return input_dict
    
    def parse_first_strand_sample(self, input_dict:dict) -> dict:
        logger.debug("Called first strand sample parser")
        input_dict['well'] = re.search(r"\s\((.*)\)$", input_dict['submitter_id']).groups()[0]
        input_dict['submitter_id'] = re.sub(r"\s\(.*\)$", "", str(input_dict['submitter_id'])).strip()
        return input_dict
    
    def grab_plates(self):
        plates = []
        for plate in self.plates:
            df = self.xl.parse(plate['sheet'], header=None)
            if isinstance(df.iat[plate['row']-1, plate['column']-1], str):
                output = RSLNamer(ctx=self.ctx, instr=df.iat[plate['row']-1, plate['column']-1]).parsed_name
            else:
                continue
            plates.append(output)
        return plates

        
class PCRParser(object):
    """
    Object to pull data from Design and Analysis PCR export file.
    TODO: Generify this object.
    """    
    def __init__(self, ctx:dict, filepath:Path|None = None) -> None:
        """
        Initializes object.

        Args:
            ctx (dict): settings passed down from gui.
            filepath (Path | None, optional): file to parse. Defaults to None.
        """        
        self.ctx = ctx
        logger.debug(f"Parsing {filepath.__str__()}")        
        if filepath == None:
            logger.error(f"No filepath given.")
            self.xl = None
        else:
            try:
                self.xl = pd.ExcelFile(filepath.__str__())
            except ValueError as e:
                logger.error(f"Incorrect value: {e}")
                self.xl = None
            except PermissionError:
                logger.error(f"Couldn't get permissions for {filepath.__str__()}. Operation might have been cancelled.")
                return
        # self.pcr = OrderedDict()
        self.pcr = {}
        namer = RSLNamer(ctx=self.ctx, instr=filepath.__str__())
        self.plate_num = namer.parsed_name
        self.submission_type = namer.submission_type
        logger.debug(f"Set plate number to {self.plate_num} and type to {self.submission_type}")
        self.samples = []
        parser = getattr(self, f"parse_{self.submission_type}")
        parser()
        

    def parse_general(self, sheet_name:str):
        """
        Parse general info rows for all types of PCR results

        Args:
            sheet_name (str): Name of sheet in excel workbook that holds info.
        """        
        df = self.xl.parse(sheet_name=sheet_name, dtype=object).fillna("")
        # self.pcr['file'] = df.iloc[1][1]
        self.pcr['comment'] = df.iloc[0][1]
        self.pcr['operator'] = df.iloc[1][1]
        self.pcr['barcode'] = df.iloc[2][1]
        self.pcr['instrument'] = df.iloc[3][1]
        self.pcr['block_type'] = df.iloc[4][1]
        self.pcr['instrument_name'] = df.iloc[5][1]
        self.pcr['instrument_serial'] = df.iloc[6][1]
        self.pcr['heated_cover_serial'] = df.iloc[7][1]
        self.pcr['block_serial'] = df.iloc[8][1]
        self.pcr['run-start'] = df.iloc[9][1]
        self.pcr['run_end'] = df.iloc[10][1]
        self.pcr['run_duration'] = df.iloc[11][1]
        self.pcr['sample_volume'] = df.iloc[12][1]
        self.pcr['cover_temp'] = df.iloc[13][1]
        self.pcr['passive_ref'] = df.iloc[14][1]
        self.pcr['pcr_step'] = df.iloc[15][1]
        self.pcr['quant_cycle_method'] = df.iloc[16][1]
        self.pcr['analysis_time'] = df.iloc[17][1]
        self.pcr['software'] = df.iloc[18][1]
        self.pcr['plugin'] = df.iloc[19][1]
        self.pcr['exported_on'] = df.iloc[20][1]
        self.pcr['imported_by'] = getuser()
        return df

    def parse_wastewater(self):
        """
        Parse specific to wastewater samples.
        """        
        df = self.parse_general(sheet_name="Results")
        column_names = ["Well", "Well Position", "Omit","Sample","Target","Task"," Reporter","Quencher","Amp Status","Amp Score","Curve Quality","Result Quality Issues","Cq","Cq Confidence","Cq Mean","Cq SD","Auto Threshold","Threshold", "Auto Baseline", "Baseline Start", "Baseline End"]
        self.samples_df = df.iloc[23:][0:]
        logger.debug(f"Dataframe of PCR results:\n\t{self.samples_df}")
        self.samples_df.columns = column_names
        logger.debug(f"Samples columns: {self.samples_df.columns}")
        well_call_df = self.xl.parse(sheet_name="Well Call").iloc[24:][0:].iloc[:,-1:]
        try:
            self.samples_df['Assessment'] = well_call_df.values
        except ValueError:
            logger.error("Well call number doesn't match sample number")
        logger.debug(f"Well call df: {well_call_df}")
        # iloc is [row][column]
        for ii, row in self.samples_df.iterrows():
            try:
                sample_obj = [sample for sample in self.samples if sample['sample'] == row[3]][0]    
            except IndexError:
                sample_obj = dict(
                    sample = row['Sample'],
                    plate_rsl = self.plate_num,
                    # elution_well = row['Well Position']
                )
            logger.debug(f"Got sample obj: {sample_obj}") 
            # logger.debug(f"row: {row}")
            # rsl_num = row[3]
            # # logger.debug(f"Looking up: {rsl_num}")
            # ww_samp = lookup_ww_sample_by_rsl_sample_number(ctx=self.ctx, rsl_number=rsl_num)
            # logger.debug(f"Got: {ww_samp}")
            if isinstance(row['Cq'], float):
                sample_obj[f"ct_{row['Target'].lower()}"] = row['Cq']
            else:
                sample_obj[f"ct_{row['Target'].lower()}"] = 0.0
            try:
                sample_obj[f"{row['Target'].lower()}_status"] = row['Assessment']
            except KeyError:
                logger.error(f"No assessment for {sample_obj['sample']}")
            # match row["Target"]:
            #     case "N1":
            #         if isinstance(row['Cq'], float):
            #             sample_obj['ct_n1'] = row["Cq"]
            #         else:
            #             sample_obj['ct_n1'] = 0.0
            #         sample_obj['n1_status'] = row['Assessment']
            #     case "N2":
            #         if isinstance(row['Cq'], float):
            #             sample_obj['ct_n2'] = row['Assessment']
            #         else:
            #             sample_obj['ct_n2'] = 0.0
            #     case _:
            #         logger.warning(f"Unexpected input for row[4]: {row["Target"]}")
            self.samples.append(sample_obj)
        

    
