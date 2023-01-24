import pandas as pd
from pathlib import Path
from backend.db.models.samples import WWSample, BCSample
import logging
from collections import OrderedDict
import re
import numpy as np
from datetime import date
import uuid

logger = logging.getLogger(f"submissions.{__name__}")

class SheetParser(object):

    def __init__(self, filepath:Path|None = None, **kwargs):
        logger.debug(f"Parsing {filepath.__str__()}")
        for kwarg in kwargs:
            setattr(self, f"_{kwarg}", kwargs[kwarg])
        if filepath == None:
            logger.debug(f"No filepath.")
            self.xl = None
        else:
            
            try:
                self.xl = pd.ExcelFile(filepath.__str__())
            except ValueError:
                self.xl = None
        self.sub = OrderedDict()
        self.sub['submission_type'] = self._type_decider()        
        parse_sub = getattr(self, f"_parse_{self.sub['submission_type'].lower()}")
        parse_sub()

    def _type_decider(self):
        try:
            for type in self._submission_types:
                if self.xl.sheet_names == self._submission_types[type]['excel_map']:
                    return type.title()
            return "Unknown"
        except:
            return "Unknown"


    def _parse_unknown(self):
        self.sub = None
    

    def _parse_generic(self, sheet_name:str):
        submission_info = self.xl.parse(sheet_name=sheet_name)
        self.sub['submitter_plate_num'] = submission_info.iloc[0][1]
        self.sub['rsl_plate_num'] = str(submission_info.iloc[10][1])
        self.sub['submitted_date'] = submission_info.iloc[1][1].date()#.strftime("%Y-%m-%d")
        self.sub['submitting_lab'] = submission_info.iloc[0][3]
        self.sub['sample_count'] = str(submission_info.iloc[2][3])
        self.sub['extraction_kit'] = submission_info.iloc[3][3]
        
        return submission_info


    def _parse_bacterial_culture(self):
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
        self.sub['lot_wash_1'] = submission_info.iloc[1][6]
        self.sub['lot_wash_2'] = submission_info.iloc[2][6]
        self.sub['lot_binding_buffer'] = submission_info.iloc[3][6]
        self.sub['lot_magnetic_beads'] = submission_info.iloc[4][6]
        self.sub['lot_lysis_buffer'] = submission_info.iloc[5][6]
        self.sub['lot_elution_buffer'] = submission_info.iloc[6][6]
        self.sub['lot_isopropanol'] = submission_info.iloc[9][6]
        self.sub['lot_ethanol'] = submission_info.iloc[10][6]
        self.sub['lot_positive_control'] = submission_info.iloc[103][1]
        self.sub['lot_plate'] = submission_info.iloc[12][6]
        sample_parser = SampleParser(submission_info.iloc[15:111])
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type'].lower()}_samples")
        logger.debug(f"Parser result: {self.sub}")
        self.sub['samples'] = sample_parse()


    def _parse_wastewater(self):
        # submission_info = self.xl.parse("WW Submissions (ENTER HERE)")
        submission_info = self._parse_generic("WW Submissions (ENTER HERE)")
        enrichment_info = self.xl.parse("Enrichment Worksheet")
        extraction_info = self.xl.parse("Extraction Worksheet")
        qprc_info = self.xl.parse("qPCR Worksheet")
        self.sub['technician'] = f"Enr: {enrichment_info.columns[2]}, Ext: {extraction_info.columns[2]}, PCR: {qprc_info.columns[2]}"
        # reagents
        self.sub['lot_lysis_buffer'] = enrichment_info.iloc[0][14]
        self.sub['lot_proteinase_K'] = enrichment_info.iloc[1][14]
        self.sub['lot_magnetic_virus_particles'] = enrichment_info.iloc[2][14]
        self.sub['lot_enrichment_reagent_1'] = enrichment_info.iloc[3][14]
        self.sub['lot_binding_buffer'] = extraction_info.iloc[0][14]
        self.sub['lot_magnetic_beads'] = extraction_info.iloc[1][14]
        self.sub['lot_wash'] = extraction_info.iloc[2][14]
        self.sub['lot_ethanol'] = extraction_info.iloc[3][14]
        self.sub['lot_elution_buffer'] = extraction_info.iloc[4][14]
        self.sub['lot_master_mix'] = qprc_info.iloc[0][14]
        self.sub['lot_pre_mix_1'] = qprc_info.iloc[1][14]
        self.sub['lot_pre_mix_2'] = qprc_info.iloc[2][14]
        self.sub['lot_positive_control'] = qprc_info.iloc[3][14]
        self.sub['lot_ddh2o'] = qprc_info.iloc[4][14]
        sample_parser = SampleParser(submission_info.iloc[16:40])
        sample_parse = getattr(sample_parser, f"parse_{self.sub['submission_type'].lower()}_samples")
        self.sub['samples'] = sample_parse()


class SampleParser(object):


    def __init__(self, df:pd.DataFrame) -> None:
        self.samples = df.to_dict("records")


    def parse_bacterial_culture_samples(self) -> list[BCSample]:
        new_list = []
        for sample in self.samples:
            new = BCSample()
            new.well_number = sample['This section to be filled in completely by submittor']
            new.sample_id = sample['Unnamed: 1']
            new.organism = sample['Unnamed: 2']
            new.concentration = sample['Unnamed: 3']
            # logger.debug(f"Sample object: {new.sample_id} = {type(new.sample_id)}")
            logger.debug(f"Got sample_id: {new.sample_id}")
            try:
                not_a_nan = not np.isnan(new.sample_id) and str(new.sample_id).lower() != 'blank'
            except TypeError:
                not_a_nan = True
            if not_a_nan:
                new_list.append(new)
        return new_list


    def parse_wastewater_samples(self) -> list[WWSample]:
        new_list = []
        for sample in self.samples:
            new = WWSample()
            new.ww_processing_num = sample['Unnamed: 2']
            try:
                not_a_nan = not np.isnan(sample['Unnamed: 3'])
            except TypeError:
                not_a_nan = True
            if not_a_nan:
                new.ww_sample_full_id = sample['Unnamed: 3']
            else:
                new.ww_sample_full_id = uuid.uuid4().hex.upper()
            new.rsl_number = sample['Unnamed: 9']
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
    