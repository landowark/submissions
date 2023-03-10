import pandas as pd
from pathlib import Path
from backend.db.models import WWSample, BCSample
import logging
from collections import OrderedDict
import re
import numpy as np
from datetime import date
import uuid
from tools import check_not_nan

logger = logging.getLogger(f"submissions.{__name__}")

class SheetParser(object):
    """
    object to pull and contain data from excel file
    """
    def __init__(self, filepath:Path|None = None, **kwargs):
        """
        Args:
            filepath (Path | None, optional): file path to excel sheet. Defaults to None.
        """
        logger.debug(f"Parsing {filepath.__str__()}")
        # set attributes based on kwargs from gui ctx
        for kwarg in kwargs:
            setattr(self, f"_{kwarg}", kwargs[kwarg])
        if filepath == None:
            logger.error(f"No filepath given.")
            self.xl = None
        else:
            try:
                self.xl = pd.ExcelFile(filepath.__str__())
            except ValueError as e:
                logger.error(f"Incorrect value: {e}")
                self.xl = None
        self.sub = OrderedDict()
        # make decision about type of sample we have
        self.sub['submission_type'] = self._type_decider()
        # select proper parser based on sample type
        parse_sub = getattr(self, f"_parse_{self.sub['submission_type'].lower()}")
        parse_sub()

    def _type_decider(self) -> str:
        """
        makes decisions about submission type based on structure of excel file

        Returns:
            str: submission type name
        """        
        try:
            for type in self._submission_types:
                if self.xl.sheet_names == self._submission_types[type]['excel_map']:
                    return type.title()
            return "Unknown"
        except Exception as e:
            logger.warning(f"We were unable to parse the submission type due to: {e}")
            return "Unknown"


    def _parse_unknown(self) -> None:
        """
        Dummy function to handle unknown excel structures
        """    
        logger.error(f"Unknown excel workbook structure. Cannot parse.")    
        self.sub = None
    

    def _parse_generic(self, sheet_name:str) -> pd.DataFrame:
        """
        Pulls information common to all submission types and passes on dataframe

        Args:
            sheet_name (str): name of excel worksheet to pull from

        Returns:
            pd.DataFrame: relevant dataframe from excel sheet
        """        
        submission_info = self.xl.parse(sheet_name=sheet_name, dtype=object)
        
        self.sub['submitter_plate_num'] = submission_info.iloc[0][1]
        self.sub['rsl_plate_num'] =  submission_info.iloc[10][1]
        self.sub['submitted_date'] = submission_info.iloc[1][1]
        self.sub['submitting_lab'] = submission_info.iloc[0][3]
        self.sub['sample_count'] = submission_info.iloc[2][3]
        self.sub['extraction_kit'] = submission_info.iloc[3][3]
        
        return submission_info


    def _parse_bacterial_culture(self) -> None:
        """
        pulls info specific to bacterial culture sample type
        """

        def _parse_reagents(df:pd.DataFrame) -> None:
            """
            Pulls reagents from the bacterial sub-dataframe

            Args:
                df (pd.DataFrame): input sub dataframe
            """            
            for ii, row in df.iterrows():
                # skip positive control
                if ii == 11:
                    continue
                logger.debug(f"Running reagent parse for {row[1]} with type {type(row[1])} and value: {row[2]} with type {type(row[2])}")
                # try:
                #     check = not np.isnan(row[1])
                # except TypeError:
                #     check = True
                if not isinstance(row[2], float) and check_not_nan(row[1]):
                    # must be prefixed with 'lot_' to be recognized by gui
                    try:
                        reagent_type = row[1].replace(' ', '_').lower().strip()
                    except AttributeError:
                        pass
                    if reagent_type == "//":
                        reagent_type = row[0].replace(' ', '_').lower().strip()
                    try:
                        output_var = row[2].upper()
                    except AttributeError:
                        logger.debug(f"Couldn't upperize {row[2]}, must be a number")
                        output_var = row[2]
                    logger.debug(f"Output variable is {output_var}")
                    # self.sub[f"lot_{reagent_type}"] = output_var
                    # update 2023-02-10 to above allowing generation of expiry date in adding reagent to db.
                    logger.debug(f"Expiry date for imported reagent: {row[3]}")
                    # try:
                    #     check = not np.isnan(row[3])
                    # except TypeError:
                    #     check = True
                    if check_not_nan(row[3]):
                        expiry = row[3].date()
                    else:
                        expiry = date.today()
                    self.sub[f"lot_{reagent_type}"] = {'lot':output_var, 'exp':expiry}
        submission_info = self._parse_generic("Sample List")
        # iloc is [row][column] and the first row is set as header row so -2
        tech = str(submission_info.iloc[11][1])
        if tech == "nan":
            tech = "Unknown"
        elif len(tech.split(",")) > 1:
            tech_reg = re.compile(r"[A-Z]{2}")
            tech = ", ".join(tech_reg.findall(tech))
        self.sub['technician'] = tech
        # reagents
        # must be prefixed with 'lot_' to be recognized by gui
        # Todo: find a more adaptable way to read reagents.

        reagent_range = submission_info.iloc[1:13, 4:8]
        _parse_reagents(reagent_range)
        # self.sub['lot_wash_1'] = submission_info.iloc[1][6] #if pd.isnull(submission_info.iloc[1][6]) else string_formatter(submission_info.iloc[1][6])
        # self.sub['lot_wash_2'] = submission_info.iloc[2][6] #if pd.isnull(submission_info.iloc[2][6]) else string_formatter(submission_info.iloc[2][6])
        # self.sub['lot_binding_buffer'] = submission_info.iloc[3][6] #if pd.isnull(submission_info.iloc[3][6]) else string_formatter(submission_info.iloc[3][6])
        # self.sub['lot_magnetic_beads'] = submission_info.iloc[4][6] #if pd.isnull(submission_info.iloc[4][6]) else string_formatter(submission_info.iloc[4][6])
        # self.sub['lot_lysis_buffer'] = submission_info.iloc[5][6] #if np.nan(submission_info.iloc[5][6]) else string_formatter(submission_info.iloc[5][6])
        # self.sub['lot_elution_buffer'] = submission_info.iloc[6][6] #if pd.isnull(submission_info.iloc[6][6]) else string_formatter(submission_info.iloc[6][6])
        # self.sub['lot_isopropanol'] = submission_info.iloc[9][6] #if pd.isnull(submission_info.iloc[9][6]) else string_formatter(submission_info.iloc[9][6])
        # self.sub['lot_ethanol'] = submission_info.iloc[10][6] #if pd.isnull(submission_info.iloc[10][6]) else string_formatter(submission_info.iloc[10][6])
        # self.sub['lot_positive_control'] = submission_info.iloc[103][1] #if pd.isnull(submission_info.iloc[103][1]) else string_formatter(submission_info.iloc[103][1])
        # self.sub['lot_plate'] = submission_info.iloc[12][6] #if pd.isnull(submission_info.iloc[12][6]) else string_formatter(submission_info.iloc[12][6])
        # get individual sample info
        sample_parser = SampleParser(submission_info.iloc[15:111])
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type'].lower()}_samples")
        logger.debug(f"Parser result: {self.sub}")
        self.sub['samples'] = sample_parse()


    def _parse_wastewater(self) -> None:
        """
        pulls info specific to wastewater sample type
        """        

        def _parse_reagents(df:pd.DataFrame) -> None:
            """
            Pulls reagents from the bacterial sub-dataframe

            Args:
                df (pd.DataFrame): input sub dataframe
            """
            # logger.debug(df)
            for ii, row in df.iterrows():
                # try:
                #     check = not np.isnan(row[5])
                # except TypeError:
                #     check = True
                if not isinstance(row[5], float) and check_not_nan(row[5]):
                    # must be prefixed with 'lot_' to be recognized by gui
                    # regex below will remove 80% from 80% ethanol in the Wastewater kit.
                    output_key = re.sub(r"^\d{1,3}%\s?", "", row[0].lower().strip().replace(' ', '_'))
                    output_key = output_key.strip("_")
                    try:
                        output_var = row[5].upper()
                    except AttributeError:
                        logger.debug(f"Couldn't upperize {row[5]}, must be a number")
                        output_var = row[5]
                    if check_not_nan(row[7]):
                        try:
                            expiry = row[7].date()
                        except AttributeError:
                            expiry = date.today()
                    else:
                        expiry = date.today()
                    self.sub[f"lot_{output_key}"] = {'lot':output_var, 'exp':expiry}
        submission_info = self._parse_generic("WW Submissions (ENTER HERE)")
        enrichment_info = self.xl.parse("Enrichment Worksheet", dtype=object)
        enr_reagent_range = enrichment_info.iloc[0:4, 9:20]
        extraction_info = self.xl.parse("Extraction Worksheet", dtype=object)
        ext_reagent_range = extraction_info.iloc[0:5, 9:20]
        qprc_info = self.xl.parse("qPCR Worksheet", dtype=object)
        pcr_reagent_range = qprc_info.iloc[0:5, 9:20]
        self.sub['technician'] = f"Enr: {enrichment_info.columns[2]}, Ext: {extraction_info.columns[2]}, PCR: {qprc_info.columns[2]}"
        _parse_reagents(enr_reagent_range)
        _parse_reagents(ext_reagent_range)
        _parse_reagents(pcr_reagent_range)
        # reagents
        # logger.debug(qprc_info)
        # self.sub['lot_lysis_buffer'] = enrichment_info.iloc[0][14] #if pd.isnull(enrichment_info.iloc[0][14]) else string_formatter(enrichment_info.iloc[0][14])
        # self.sub['lot_proteinase_K'] = enrichment_info.iloc[1][14] #if pd.isnull(enrichment_info.iloc[1][14]) else string_formatter(enrichment_info.iloc[1][14]) 
        # self.sub['lot_magnetic_virus_particles'] = enrichment_info.iloc[2][14] #if pd.isnull(enrichment_info.iloc[2][14]) else string_formatter(enrichment_info.iloc[2][14])
        # self.sub['lot_enrichment_reagent_1'] = enrichment_info.iloc[3][14] #if pd.isnull(enrichment_info.iloc[3][14]) else string_formatter(enrichment_info.iloc[3][14])
        # self.sub['lot_binding_buffer'] = extraction_info.iloc[0][14] #if pd.isnull(extraction_info.iloc[0][14]) else string_formatter(extraction_info.iloc[0][14])
        # self.sub['lot_magnetic_beads'] = extraction_info.iloc[1][14] #if pd.isnull(extraction_info.iloc[1][14]) else string_formatter(extraction_info.iloc[1][14])
        # self.sub['lot_wash'] = extraction_info.iloc[2][14] #if pd.isnull(extraction_info.iloc[2][14]) else string_formatter(extraction_info.iloc[2][14])
        # self.sub['lot_ethanol'] = extraction_info.iloc[3][14] #if pd.isnull(extraction_info.iloc[3][14]) else string_formatter(extraction_info.iloc[3][14])
        # self.sub['lot_elution_buffer'] = extraction_info.iloc[4][14] #if pd.isnull(extraction_info.iloc[4][14]) else string_formatter(extraction_info.iloc[4][14])
        # self.sub['lot_master_mix'] = qprc_info.iloc[0][14] #if pd.isnull(qprc_info.iloc[0][14]) else string_formatter(qprc_info.iloc[0][14])
        # self.sub['lot_pre_mix_1'] = qprc_info.iloc[1][14] #if pd.isnull(qprc_info.iloc[1][14]) else string_formatter(qprc_info.iloc[1][14])
        # self.sub['lot_pre_mix_2'] = qprc_info.iloc[2][14] #if pd.isnull(qprc_info.iloc[2][14]) else string_formatter(qprc_info.iloc[2][14])
        # self.sub['lot_positive_control'] = qprc_info.iloc[3][14] #if pd.isnull(qprc_info.iloc[3][14]) else string_formatter(qprc_info.iloc[3][14])
        # self.sub['lot_ddh2o'] = qprc_info.iloc[4][14] #if pd.isnull(qprc_info.iloc[4][14]) else string_formatter(qprc_info.iloc[4][14])
        # get individual sample info
        sample_parser = SampleParser(submission_info.iloc[16:40])
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type'].lower()}_samples")
        self.sub['samples'] = sample_parse()


class SampleParser(object):
    """
    object to pull data for samples in excel sheet and construct individual sample objects
    """

    def __init__(self, df:pd.DataFrame) -> None:
        self.samples = df.to_dict("records")


    def parse_bacterial_culture_samples(self) -> list[BCSample]:
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
        return new_list


    def parse_wastewater_samples(self) -> list[WWSample]:
        """
        construct wastewater specific sample objects

        Returns:
            list[WWSample]: list of sample objects
        """        
        new_list = []
        for sample in self.samples:
            new = WWSample()
            new.ww_processing_num = sample['Unnamed: 2']
            # need to ensure we have a sample id for database integrity
            try:
                not_a_nan = not np.isnan(sample['Unnamed: 3'])
            except TypeError:
                not_a_nan = True
            if not_a_nan:
                new.ww_sample_full_id = sample['Unnamed: 3']
            else:
                new.ww_sample_full_id = uuid.uuid4().hex.upper()
            new.rsl_number = sample['Unnamed: 9']
            # need to ensure we get a collection date
            try:
                not_a_nan = not np.isnan(sample['Unnamed: 5'])
            except TypeError:
                not_a_nan = True
            if not_a_nan:
                new.collection_date = sample['Unnamed: 5']
            else:
                new.collection_date = date.today()
            new.testing_type = sample['Unnamed: 6']
            new.site_status = sample['Unnamed: 7']
            new.notes = str(sample['Unnamed: 8'])
            new.well_number = sample['Unnamed: 1']
            new_list.append(new)
        return new_list
