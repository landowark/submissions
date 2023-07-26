'''
contains parser object for pulling values from client generated submission sheets.
'''
from getpass import getuser
import pprint
from typing import Tuple
import pandas as pd
from pathlib import Path
from backend.db.models import WWSample, BCSample
from backend.db import lookup_ww_sample_by_ww_sample_num
from backend.pydant import PydSubmission, PydReagent
import logging
from collections import OrderedDict
import re
import numpy as np
from datetime import date, datetime
import uuid
from tools import check_not_nan, RSLNamer, massage_common_reagents, convert_nans_to_nones, Settings

logger = logging.getLogger(f"submissions.{__name__}")

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
        # select proper parser based on sample type
        parse_sub = getattr(self, f"parse_{self.sub['submission_type'].lower()}")
        parse_sub()
        # self.calculate_column_count()

    def type_decider(self) -> str:
        """
        makes decisions about submission type based on structure of excel file

        Returns:
            str: submission type name
        """        
        # Check metadata for category, return first category
        if self.xl.book.properties.category != None:
            logger.debug("Using file properties to find type...")
            categories = [item.strip().title() for item in self.xl.book.properties.category.split(";")]
            return categories[0].replace(" ", "_")
        else:
            # This code is going to be depreciated once there is full adoption of the client sheets
            # with updated metadata... but how will it work for Artic?
            logger.debug("Using excel map to find type...")
            try:
                for type in self.ctx.submission_types:
                    # This gets the *first* submission type that matches the sheet names in the workbook 
                    if self.xl.sheet_names == self.ctx.submission_types[type]['excel_map']:
                        return type.title()
                return "Unknown"
            except Exception as e:
                logger.warning(f"We were unable to parse the submission type due to: {e}")
                return "Unknown"

    def parse_unknown(self) -> None:
        """
        Dummy function to handle unknown excel structures
        """    
        logger.error(f"Unknown excel workbook structure. Cannot parse.")    
        self.sub = None
    
    def parse_generic(self, sheet_name:str) -> pd.DataFrame:
        """
        Pulls information common to all wasterwater/bacterial culture types and passes on dataframe

        Args:
            sheet_name (str): name of excel worksheet to pull from

        Returns:
            pd.DataFrame: relevant dataframe from excel sheet
        """      
        # self.xl is a pd.ExcelFile so we need to parse it into a df  
        submission_info = self.xl.parse(sheet_name=sheet_name, dtype=object)
        self.sub['submitter_plate_num'] = submission_info.iloc[0][1]
        if check_not_nan(submission_info.iloc[10][1]):
            self.sub['rsl_plate_num'] =  RSLNamer(ctx=self.ctx, instr=submission_info.iloc[10][1]).parsed_name
        else:
            # self.sub['rsl_plate_num'] =  RSLNamer(self.filepath).parsed_name
            self.sub['rsl_plate_num'] = None
        self.sub['submitted_date'] = submission_info.iloc[1][1]
        self.sub['submitting_lab'] = submission_info.iloc[0][3]
        self.sub['sample_count'] = submission_info.iloc[2][3]
        self.sub['extraction_kit'] = submission_info.iloc[3][3]
        if check_not_nan(submission_info.iloc[1][3]):
            self.sub['submission_type'] = dict(value=submission_info.iloc[1][3], parsed=True)
        else:
            self.sub['submission_type'] = dict(value=self.sub['submission_type'], parsed=False)
        return submission_info

    def parse_bacterial_culture(self) -> None:
        """
        pulls info specific to bacterial culture sample type
        """

        def parse_reagents(df:pd.DataFrame) -> None:
            """
            Pulls reagents from the bacterial sub-dataframe

            Args:
                df (pd.DataFrame): input sub dataframe
            """            
            for ii, row in df.iterrows():
                # skip positive control
                logger.debug(f"Running reagent parse for {row[1]} with type {type(row[1])} and value: {row[2]} with type {type(row[2])}")
                # if the lot number isn't a float and the reagent type isn't blank
                # if not isinstance(row[2], float) and check_not_nan(row[1]):
                if check_not_nan(row[1]):
                    # must be prefixed with 'lot_' to be recognized by gui
                    # This is no longer true since reagents are loaded into their own key in dictionary
                    try:
                        reagent_type = row[1].replace(' ', '_').lower().strip()
                    except AttributeError:
                        pass
                    # If there is a double slash in the type field, such as ethanol/iso
                    # Use the cell to the left for reagent type.
                    if reagent_type == "//":
                        if check_not_nan(row[2]):
                            reagent_type = row[0].replace(' ', '_').lower().strip()
                        else:
                            continue
                    try:
                        output_var = convert_nans_to_nones(str(row[2]).upper())
                    except AttributeError:
                        logger.debug(f"Couldn't upperize {row[2]}, must be a number")
                        output_var = convert_nans_to_nones(str(row[2]))
                    logger.debug(f"Output variable is {output_var}")
                    logger.debug(f"Expiry date for imported reagent: {row[3]}")
                    if check_not_nan(row[3]):
                        try:
                            expiry = row[3].date()
                        except AttributeError as e:
                            try:
                                expiry = datetime.strptime(row[3], "%Y-%m-%d")
                            except TypeError as e:
                                expiry = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + row[3] - 2)
                    else:
                        logger.debug(f"Date: {row[3]}")
                        # expiry = date.today()
                        expiry = date(year=1970, month=1, day=1)
                    # self.sub[f"lot_{reagent_type}"] = {'lot':output_var, 'exp':expiry}
                    # self.sub['reagents'].append(dict(type=reagent_type, lot=output_var, exp=expiry))
                    self.sub['reagents'].append(PydReagent(type=reagent_type, lot=output_var, exp=expiry))
        submission_info = self.parse_generic("Sample List")
        # iloc is [row][column] and the first row is set as header row so -2
        self.sub['technician'] = str(submission_info.iloc[11][1])
        # reagents
        # must be prefixed with 'lot_' to be recognized by gui
        # This is no longer true wince the creation of self.sub['reagents']
        self.sub['reagents'] = []
        reagent_range = submission_info.iloc[1:14, 4:8]
        logger.debug(reagent_range)
        parse_reagents(reagent_range)
        # get individual sample info
        sample_parser = SampleParser(self.ctx, submission_info.iloc[16:112])
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type']['value'].replace(' ', '_').lower()}_samples")
        logger.debug(f"Parser result: {self.sub}")
        self.sample_result, self.sub['samples'] = sample_parse()

    def parse_wastewater(self) -> None:
        """
        pulls info specific to wastewater sample type
        """        
        def retrieve_elution_map():
            full = self.xl.parse("Extraction Worksheet")
            elu_map = full.iloc[9:18, 5:]
            elu_map.set_index(elu_map.columns[0], inplace=True)
            elu_map.columns = elu_map.iloc[0]
            elu_map = elu_map.tail(-1)
            return elu_map
        def parse_reagents(df:pd.DataFrame) -> None:
            """
            Pulls reagents from the bacterial sub-dataframe

            Args:
                df (pd.DataFrame): input sub dataframe
            """
            # iterate through sub-df rows
            for ii, row in df.iterrows():
                logger.debug(f"Parsing this row for reagents: {row}")
                if check_not_nan(row[5]):
                    # must be prefixed with 'lot_' to be recognized by gui
                    # regex below will remove 80% from 80% ethanol in the Wastewater kit.
                    output_key = re.sub(r"^\d{1,3}%\s?", "", row[0].lower().strip().replace(' ', '_'))
                    output_key = output_key.strip("_")
                    # output_var is the lot number
                    try:
                        output_var = convert_nans_to_nones(str(row[5].upper()))
                    except AttributeError:
                        logger.debug(f"Couldn't upperize {row[5]}, must be a number")
                        output_var = convert_nans_to_nones(str(row[5]))
                    if check_not_nan(row[7]):
                        try:
                            expiry = row[7].date()
                        except AttributeError:
                            expiry = date.today()
                    else:
                        expiry = date.today()
                    logger.debug(f"Expiry date for {output_key}: {expiry} of type {type(expiry)}")
                    # self.sub[f"lot_{output_key}"] = {'lot':output_var, 'exp':expiry}
                    # self.sub['reagents'].append(dict(type=output_key, lot=output_var, exp=expiry))
                    reagent = PydReagent(type=output_key, lot=output_var, exp=expiry)
                    logger.debug(f"Here is the created reagent: {reagent}")
                    self.sub['reagents'].append(reagent)
        # parse submission sheet
        submission_info = self.parse_generic("WW Submissions (ENTER HERE)")
        # parse enrichment sheet
        enrichment_info = self.xl.parse("Enrichment Worksheet", dtype=object)
        # set enrichment reagent range
        enr_reagent_range = enrichment_info.iloc[0:4, 9:20]
        # parse extraction sheet
        extraction_info = self.xl.parse("Extraction Worksheet", dtype=object)
        # set extraction reagent range 
        ext_reagent_range = extraction_info.iloc[0:5, 9:20]
        # parse qpcr sheet
        qprc_info = self.xl.parse("qPCR Worksheet", dtype=object)
        # set qpcr reagent range
        pcr_reagent_range = qprc_info.iloc[0:5, 9:20]
        # compile technician info from all sheets
        if all(map(check_not_nan, [enrichment_info.columns[2], extraction_info.columns[2], qprc_info.columns[2]])):
            parsed = True
        else:
            parsed = False
        self.sub['technician'] = dict(value=f"Enr: {enrichment_info.columns[2]}, Ext: {extraction_info.columns[2]}, PCR: {qprc_info.columns[2]}", parsed=parsed)
        self.sub['reagents'] = []
        parse_reagents(enr_reagent_range)
        parse_reagents(ext_reagent_range)
        parse_reagents(pcr_reagent_range)
        # parse samples
        sample_parser = SampleParser(self.ctx, submission_info.iloc[16:], elution_map=retrieve_elution_map())
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type']['value'].lower()}_samples")
        self.sample_result, self.sub['samples'] = sample_parse()
        self.sub['csv'] = self.xl.parse("Copy to import file", dtype=object)

    def parse_wastewater_artic(self) -> None:
        """
        pulls info specific to wastewater_arctic submission type
        """
        self.sub['submission_type'] = dict(value=self.sub['submission_type'], parsed=True)
        def parse_reagents(df:pd.DataFrame):
            logger.debug(df)
            for ii, row in df.iterrows():
                if check_not_nan(row[0]):
                    try:
                        output_key = re.sub(r"\(.+?\)", "", row[0].lower().strip().replace(' ', '_'))
                    except AttributeError:
                        continue
                    output_key = output_key.strip("_")
                    output_key = massage_common_reagents(output_key)
                    try:
                        output_var = convert_nans_to_nones(str(row[1].upper()))
                    except AttributeError:
                        logger.debug(f"Couldn't upperize {row[1]}, must be a number")
                        output_var = convert_nans_to_nones(str(row[1]))
                    logger.debug(f"Output variable is {output_var}")
                    logger.debug(f"Expiry date for imported reagent: {row[2]}")
                    if check_not_nan(row[2]):
                        try:
                            expiry = row[2].date()
                        except AttributeError as e:
                            try:
                                expiry = datetime.strptime(row[2], "%Y-%m-%d")
                            except TypeError as e:
                                expiry = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + row[2] - 2)
                            except ValueError as e:
                                continue
                    else:
                        logger.debug(f"Date: {row[2]}")
                        expiry = date.today()
                    # self.sub['reagents'].append(dict(type=output_key, lot=output_var, exp=expiry))
                    self.sub['reagents'].append(PydReagent(type=output_key, lot=output_var, exp=expiry))
                else:
                    continue
        def massage_samples(df:pd.DataFrame) -> pd.DataFrame:
            df.set_index(df.columns[0], inplace=True)
            df.columns = df.iloc[0]
            logger.debug(f"df to massage\n: {df}")
            return_list = []
            for _, ii in df.iloc[1:,1:].iterrows():
                for c in df.columns.to_list():
                    if not check_not_nan(c):
                        continue
                    logger.debug(f"Checking {ii.name}{c}")
                    if check_not_nan(df.loc[ii.name, int(c)]) and df.loc[ii.name, int(c)] != "EMPTY":
                        try:
                            return_list.append(dict(sample_name=re.sub(r"\s?\(.*\)", "", df.loc[ii.name, int(c)]), \
                                                well=f"{ii.name}{c}",
                                                artic_plate=self.sub['rsl_plate_num']))
                        except TypeError as e:
                            logger.error(f"Got an int for {c}, skipping.")
                            continue
            logger.debug(f"massaged sample list for {self.sub['rsl_plate_num']}: {pprint.pprint(return_list)}")
            return return_list
        submission_info = self.xl.parse("First Strand", dtype=object)
        biomek_info = self.xl.parse("ArticV4 Biomek", dtype=object)
        sub_reagent_range = submission_info.iloc[56:, 1:4].dropna(how='all')
        biomek_reagent_range = biomek_info.iloc[60:, 0:3].dropna(how='all')
        # submission_info = self.xl.parse("cDNA", dtype=object)
        # biomek_info = self.xl.parse("ArticV4_1 Biomek", dtype=object)
        # # Reminder that the iloc uses row, column ordering
        # # sub_reagent_range = submission_info.iloc[56:, 1:4].dropna(how='all')
        # sub_reagent_range = submission_info.iloc[7:15, 5:9].dropna(how='all')
        # biomek_reagent_range = biomek_info.iloc[62:, 0:3].dropna(how='all')
        self.sub['submitter_plate_num'] = ""
        self.sub['rsl_plate_num'] =  RSLNamer(ctx=self.ctx, instr=self.filepath.__str__()).parsed_name
        self.sub['submitted_date'] = biomek_info.iloc[1][1]
        self.sub['submitting_lab'] = "Enterics Wastewater Genomics"
        self.sub['sample_count'] = submission_info.iloc[4][6]
        # self.sub['sample_count'] = submission_info.iloc[34][6]
        self.sub['extraction_kit'] = "ArticV4.1"
        self.sub['technician'] = f"MM: {biomek_info.iloc[2][1]}, Bio: {biomek_info.iloc[3][1]}"
        self.sub['reagents'] = []
        parse_reagents(sub_reagent_range)
        parse_reagents(biomek_reagent_range)
        samples = massage_samples(biomek_info.iloc[22:31, 0:])
        # samples = massage_samples(biomek_info.iloc[25:33, 0:])
        sample_parser = SampleParser(self.ctx, pd.DataFrame.from_records(samples))
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type']['value'].lower()}_samples")
        self.sample_result, self.sub['samples'] = sample_parse()
        
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

    
class SampleParser(object):
    """
    object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, ctx:Settings, df:pd.DataFrame, elution_map:pd.DataFrame|None=None) -> None:
        """
        convert sample sub-dataframe to dictionary of records

        Args:
            ctx (Settings): settings object passed down from gui
            df (pd.DataFrame): input sample dataframe
            elution_map (pd.DataFrame | None, optional): optional map of elution plate. Defaults to None.
        """        
        self.ctx = ctx
        self.samples = df.to_dict("records")
        self.elution_map = elution_map


    def parse_bacterial_culture_samples(self) -> Tuple[str|None, list[BCSample]]:
        """
        construct bacterial culture specific sample objects

        Returns:
            list[BCSample]: list of sample objects
        """       
        # logger.debug(f"Samples: {self.samples}") 
        new_list = []
        for sample in self.samples:
            new = BCSample()
            new.well_number = sample['This section to be filled in completely by submittor']
            new.sample_id = sample['Unnamed: 1']
            new.organism = sample['Unnamed: 2']
            new.concentration = sample['Unnamed: 3']
            # logger.debug(f"Sample object: {new.sample_id} = {type(new.sample_id)}")
            logger.debug(f"Got sample_id: {new.sample_id}")
            # need to exclude empties and blanks
            try:
                not_a_nan = not np.isnan(new.sample_id) and str(new.sample_id).lower() != 'blank'
            except TypeError:
                not_a_nan = True
            if not_a_nan:
                new_list.append(new)
        return None, new_list


    def parse_wastewater_samples(self) -> Tuple[str|None, list[WWSample]]:
        """
        construct wastewater specific sample objects

        Returns:
            list[WWSample]: list of sample objects
        """        
        def search_df_for_sample(sample_rsl:str):
            logger.debug(f"Attempting to find sample {sample_rsl} in \n {self.elution_map}")
            well = self.elution_map.where(self.elution_map==sample_rsl)
            # logger.debug(f"Well: {well}")
            well = well.dropna(how='all').dropna(axis=1, how="all")
            if well.size > 1:
                well = well.iloc[0].to_frame().dropna().T
            logger.debug(f"well {sample_rsl} post processing: {well.size}: {type(well)}, {well.index[0]}, {well.columns[0]}")
            self.elution_map.at[well.index[0], well.columns[0]] = np.nan
            try:
                col = str(int(well.columns[0])).zfill(2)
            except ValueError:
                col = str(well.columns[0]).zfill(2)
            except TypeError as e:
                logger.error(f"Problem parsing out column number for {well}:\n {e}")
            return f"{well.index[0]}{col}"
        new_list = []
        return_val = None
        for sample in self.samples:
            new = WWSample()
            if check_not_nan(sample["Unnamed: 7"]):
                new.rsl_number = sample['Unnamed: 7'] # previously Unnamed: 9
            else:
                logger.error(f"No RSL sample number found for this sample.")
                continue
            new.ww_processing_num = sample['Unnamed: 2']
            # need to ensure we have a sample id for database integrity
            # if we don't have a sample full id, make one up
            if check_not_nan(sample['Unnamed: 3']):
                new.ww_sample_full_id = sample['Unnamed: 3']
            else:
                new.ww_sample_full_id = uuid.uuid4().hex.upper()
            # need to ensure we get a collection date
            if check_not_nan(sample['Unnamed: 5']):
                new.collection_date = sample['Unnamed: 5']
            else:
                new.collection_date = date.today()
            # new.testing_type = sample['Unnamed: 6']
            # new.site_status = sample['Unnamed: 7']
            new.notes = str(sample['Unnamed: 6']) # previously Unnamed: 8
            new.well_24 = sample['Unnamed: 1']
            elu_well = search_df_for_sample(new.rsl_number)
            if elu_well != None:
                row = elu_well[0]
                col = elu_well[1:].zfill(2)
                new.well_number = f"{row}{col}"
            else:
                # try:
                return_val += f"{new.rsl_number}\n"
                # except TypeError:
                    # return_val = f"{new.rsl_number}\n"
            new_list.append(new)
        return return_val, new_list
    
    def parse_wastewater_artic_samples(self) -> Tuple[str|None, list[WWSample]]:
        """
        The artic samples are the wastewater samples that are to be sequenced
        So we will need to lookup existing ww samples and append Artic well # and plate relation

        Returns:
            list[WWSample]: list of wastewater samples to be updated
        """        
        new_list = []
        missed_samples = []
        for sample in self.samples:
            with self.ctx.database_session.no_autoflush:
                instance = lookup_ww_sample_by_ww_sample_num(ctx=self.ctx, sample_number=sample['sample_name'])
            logger.debug(f"Checking: {sample['sample_name']}")
            if instance == None:
                logger.error(f"Unable to find match for: {sample['sample_name']}")
                missed_samples.append(sample['sample_name'])
                continue
            logger.debug(f"Got instance: {instance.ww_sample_full_id}")
            if sample['well'] != None:
                row = sample['well'][0]
                col = sample['well'][1:].zfill(2)
                sample['well'] = f"{row}{col}"
            instance.artic_well_number = sample['well']
            new_list.append(instance)
        missed_str = "\n\t".join(missed_samples)
        return f"Could not find matches for the following samples:\n\t {missed_str}", new_list


class PCRParser(object):
    """
    Object to pull data from Design and Analysis PCR export file.
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
        


            
