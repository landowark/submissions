"""
Handles display of control charts

### Currently not implemented. Requires updating to models.Results ###

"""
from datetime import datetime
from pprint import pformat
from PyQt6.QtWidgets import (
    QCheckBox, QLabel, QWidget, QComboBox, QPushButton
)
from gql import gql, Client
from gql.transport.exceptions import TransportConnectionFailed
from backend.excel.reports import ChartReportMaker
from tools import Report, report_result, clean_string
from frontend.visualizations import KrakenFigure
from .info_tab import InfoPane
from gql.transport.requests import RequestsHTTPTransport
from base64 import b64encode
import requests, io, csv, sys, logging, pandas as pd, re

from decimal import Decimal

logger = logging.getLogger(f"submissions.{__name__}")


class KrakenViewer(InfoPane):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        from backend.db.models import ResultsType
        results_type = ResultsType.query(name="Irida Kraken", limit=1)
        if not results_type:
            raise ValueError("Could not find results type Irida Kraken")
        self.projects = results_type.saved_settings['projects']
        # NOTE: set tab2 layout
        self.project_box = QComboBox()
        # NOTE: fetch types of control
        self.project_box.addItems([""] + [key for key in self.projects.keys()])
        # NOTE: create custom widget to get types of analysis -- disabled by PCR control
        # NOTE: create check box to indicate 'metadata only'
        self.metadata_box = QCheckBox()
        self.metadata_box.setChecked(True)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        self.layout.addWidget(self.project_box, 1, 0, 1, 2)
        self.layout.addWidget(QLabel("Metadata Only"), 1, 2, 1, 1)
        self.layout.addWidget(self.metadata_box, 1, 3, 1, 1)
        self.update_data()
        self.project_box.currentIndexChanged.connect(self.update_data)
        self.metadata_box.checkStateChanged.connect(self.update_data)
        self.save_button.pressed.connect(self.save_png)
        self.export_button.pressed.connect(self.save_excel)

    @classmethod
    def parse_value(cls, key, value):
        if key == "taxonomy_id":
            return value
        elif key == "fraction_total_reads":
            return Decimal(value).__float__()
        elif key in ["taxonomy_lvl", "meta.id"]:
            return value
        else:
            try:
                return int(value)
            except ValueError:
                return value
        
    @classmethod
    def read_csv_from_url(cls, url):
        """Downloads a CSV from a URL and returns a list of dictionaries."""
        try:
            response = requests.get(url)
            response.raise_for_status()  # Check for HTTP errors
            
            # Use StringIO to treat the string as a file-like object for the csv library
            f = io.StringIO(response.text)
            reader = csv.DictReader(f)
            return [row for row in reader]
        except Exception as e:
            logger.error(f"  [!] Failed to read CSV: {e}")
            return None

    @classmethod
    def read_metadata(cls, input_dict):
        output = []
        
        # Extract the base meta.id from the filename 
        # (Extracts 'MCS-Mar2026P6-20260331' from the string)
        filename = input_dict.get('reads.1', '')
        meta_id = filename.split('_S')[0] if '_S' in filename else ""
        
        # Get the taxonomy level
        tax_lvl = input_dict.get('taxonomy_level', '')

        # We need to find how many abundance entries exist (1, 2, 3...)
        # We'll also include 'unclassified' as it follows a similar pattern
        targets = []
        for key in input_dict.keys():
            if key.startswith('abundance_') and key.endswith('_name'):
                # Extract the number (e.g., '1' from 'abundance_1_name')
                num = key.split('_')[1]
                targets.append(num)
        
        # Add unclassified to the processing list if it exists
        keys_to_process = targets + (['unclassified'] if 'unclassified_name' in input_dict else [])

        for i in keys_to_process:
            prefix = f"abundance_{i}" if i != 'unclassified' else 'unclassified'
            
            name = input_dict.get(f"{prefix}_name")
            if not name:
                continue

            output.append({
                'name': name,
                'added_reads': 0, # Not present in source, defaulting to 0
                'fraction_total_reads': float(input_dict.get(f"{prefix}_fraction_total_reads", 0)),
                'kraken_assigned_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
                'meta.id': meta_id,
                'new_est_reads': int(input_dict.get(f"{prefix}_num_assigned_reads", 0)),
                'taxonomy_id': input_dict.get(f"{prefix}_ncbi_taxonomy_id", ""),
                'taxonomy_lvl': tax_lvl
            })

        return output

    

    def grab_data(self, project: str, start_date: str, end_date: str, metadata_only: bool = True):
            
        from tools import ctx

        API_TOKEN = b64encode(f"{ctx.irida_next.email}:{ctx.irida_next.token}".encode('utf-8')).decode('utf-8')  # Pulls token from config and encodes for HTTP header
        PAGE_SIZE = 5  # Number of samples per request
        

        # ==== SETUP GRAPHQL CLIENT ====
        transport = RequestsHTTPTransport(
            url = ctx.irida_next.endpoint,
            headers = {
                "Authorization": f"Basic {API_TOKEN}",
                "Content-Type": "application/json"
            },
            verify=True,  # Set to False if using self-signed certs
            retries=3
        )

        client = Client(transport=transport, fetch_schema_from_transport=False)

        output = []
        
        # Query 1: Get basic sample info (Low complexity)
        list_samples_query = gql("""
            query ListSamples($projectId: ID!, $first: Int, $after: String, $startDate: ValueScalar, $endDate: ValueScalar) {
            project(puid: $projectId) {
                samples(
                first: $first, 
                after: $after, 
                filter: { 
                    advanced_search: [
                    { 
                        field: "created_at", 
                        operator: GREATER_THAN_EQUALS, 
                        value: $startDate 
                    },
                    { 
                        field: "created_at", 
                        operator: LESS_THAN_EQUALS, 
                        value: $endDate 
                    }
                    ]
                }
                ) {
                edges {
                    node {
                    id
                    name
                    updatedAt
                    createdAt
                    metadata
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
                }
            }
            }
        """)
        

        # Query 2: Get attachments for a specific sample ID
        sample_details_query = gql("""
            query GetSampleAttachments($sampleId: ID!) {
                node(id: $sampleId) {
                ... on Sample {
                    attachments {
                    edges {
                        node {
                        filename
                        attachmentUrl
                        }
                    }
                    }
                }
                }
            }
        """)


        # def fetch_all_samples_with_data():
        all_samples = []
        after_cursor = None
        # Format must be a string since we changed the variable type to String
        

        # Step 1: Fetch Sample IDs (Low Complexity)
        while True:
            variables = {"projectId": project, "first": PAGE_SIZE, "after": after_cursor, "startDate": start_date, "endDate": end_date}
            result = client.execute(list_samples_query, variable_values=variables)
            samples_data = result["project"]["samples"]
            
            for edge in samples_data["edges"]:
                all_samples.append(edge["node"])

            if not samples_data["pageInfo"]["hasNextPage"]:
                break
            after_cursor = samples_data["pageInfo"]["endCursor"]

        # Step 2: Get data and attachments and process CSVs (if requested by user)
        for sample in all_samples:
            regex = r"(20\d{2}-?\d{2}-?\d{2})(?:-\d+)?$"
            match = re.search(regex, sample['name'])
            if match:
                raw_date = match.group(1)
                # Remove dashes if present for consistent strptime
                clean_date = raw_date.replace("-", "")
                try:
                    date_obj = datetime.strptime(clean_date, "%Y%m%d")
                except ValueError as e:
                    print(f"Date format {clean_date} in sample name '{sample['name']}' is not recognized. Expected format YYYYMMDD or YYYY-MM-DD.")
                    raise e
            else:
                date_obj = datetime.strptime(sample['createdAt'], "%Y-%m-%dT%H:%M:%SZ")
            if date_obj < self.start_date and date_obj > self.end_date:
                continue
            if metadata_only:
                sample['data'] = self.read_metadata(sample['metadata'])
                sample['filename'] = "metadata"
            else:    
                details = client.execute(sample_details_query, variable_values={"sampleId": sample["id"]})
                attachments = details["node"]["attachments"]["edges"]    
                for edge in attachments:
                    file_node = edge["node"]
                    filename = file_node["filename"]
                    url = file_node["attachmentUrl"]
                    
                    # Logic to check for .csv extension
                    if filename.lower().endswith('.csv'):
                        csv_data = self.read_csv_from_url(url)
                        if csv_data:
                            for item in csv_data:
                                item['name'] = clean_string(item['name'].split(" ")[0])
                            sample["filename"] = filename,
                            sample["data"] = csv_data
            try:
                del sample['metadata']
            except KeyError:
                pass
            try:
                for item in sample['data']:
                    item['submitted_date'] = date_obj
            except KeyError:
                continue
            output.append(sample)
        return output
            

    @report_result
    def update_data(self, *args, **kwargs):
        """
        Get control based on start/end dates
        """
        super().update_data()
        # NOTE: mode_sub_type defaults to disabled
        self.project = self.projects.get(self.project_box.currentText(), None)
        if not self.project:
            self.webview.setHtml("<html></html>")
            return
        start_date = datetime.combine(self.start_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_date = datetime.combine(self.end_date, datetime.max.time()).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            self.data = self.grab_data(project=self.project, start_date=start_date, end_date=end_date, metadata_only=self.metadata_box.isChecked())
        except TransportConnectionFailed:
            pass
        # NOTE: added in allowed to have subtypes in case additions made in future.
        self.chart_maker_function()


    def merge_genera(self, df):

        # 1. Aggressive cleaning to ensure exact matches
        # This strips whitespace and forces everything to the same type
        df['name'] = df['name'].astype(str).str.title()
        for col in ['meta.id', 'name']:
            df[col] = df[col].astype(str).str.strip()

        # 2. Identify all numeric vs non-numeric columns automatically
        # This ensures we don't miss any extra fields while summing reads
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        other_cols = [c for c in df.columns if c not in numeric_cols and c not in ['meta.id', 'name']]

        # 3. Create the Aggregation Map
        # Sum the counts/fractions, take the 'first' for dates/metadata
        agg_map = {col: 'sum' for col in numeric_cols}
        agg_map.update({col: 'first' for col in other_cols})

        # 4. Perform the GroupBy
        merged_df = df.groupby(['meta.id', 'name'], as_index=False).agg(agg_map)

        numeric_reads = pd.to_numeric(merged_df['kraken_assigned_reads'], errors='coerce')

        # 2. Use the numeric series to calculate the fractions
        merged_df['fraction_total_reads'] = merged_df.groupby('meta.id')['kraken_assigned_reads'].transform(
            lambda x: pd.to_numeric(x, errors='coerce').sum()
        )

        # 3. Perform the division, handling the 'divide by zero' case
        merged_df['fraction_total_reads'] = numeric_reads / merged_df['fraction_total_reads']
        merged_df['fraction_total_reads'] = merged_df['fraction_total_reads'].fillna(0)

        return merged_df

    @report_result
    def chart_maker_function(self, *args, **kwargs):
        """
        Create html chart for control reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        # NOTE: set the mode_sub_type for kraken. Disabled in PCRControl
        months = self.diff_month(self.start_date, self.end_date)
        # NOTE: query all control using the type/start and end dates from the gui
        chart_settings = dict(
            project=self.project,
            start_date=self.start_date,
            end_date=self.end_date,
            parent=self,
            months=months,
            species_or_genus = "Species" if self.metadata_box.isChecked() else "Genus"
        )
        try:
            df = pd.json_normalize(
                self.data, 
                record_path=['data']
            )
        except KeyError as e:
            
            logger.error(f"Data structure: {pformat([item.keys() for item in self.data])}")
            raise e
        if not self.metadata_box.isChecked():
            df = self.merge_genera(df)
        self.fig = KrakenFigure(df=df, settings=chart_settings)
        self.report_obj = ChartReportMaker(df=self.fig.df)
        if issubclass(self.fig.__class__, KrakenFigure):
            self.save_button.setEnabled(True)
        # NOTE: construct html for webview
        # if self.metadata_box.isChecked():
        #     name = "metadata"
        # else:
        #     name = "fulldata"
        # try:
        #     self.fig.df.to_csv(f"{name}_test.csv")
        # except PermissionError:
        #     pass
        self.webview.setHtml(self.fig.html)
        self.webview.update()
        return report
