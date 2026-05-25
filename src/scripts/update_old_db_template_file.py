import pyodbc
import sys, tkinter.filedialog
from pathlib import Path
from os import environ
from dotenv import load_dotenv

load_dotenv()



def main():

    # 1. Configuration - Update these with your actual server details
    server = environ.get('SQL_SERVER', None)
    database = environ.get('SQL_DATABASE', None)

    if not server or not database:
        print("Error: SQL_SERVER and SQL_DATABASE environment variables must be set.")
        sys.exit(1)
    else:
        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        print(f"Connection: {conn_str}")

    file_path = tkinter.filedialog.askopenfilename(title="Select the Excel file to upload", filetypes=[("Excel files", "*.xlsx *.xls")])
    
    try:
        file_path = Path(file_path)
        if not file_path.is_file():
            raise ValueError("The specified file does not exist.")
        if not file_path.suffix in ['.xlsx', '.xls']:
            raise ValueError("The selected file is not an Excel file.")
    except ValueError as ve:
        print(f"Invalid input: {ve}")
        sys.exit(1)

    row_number = input("Enter the row number to update (1 for the first row): ")
    try:
        row_number = int(row_number)
        if row_number < 1:
            raise ValueError("Row number must be a positive integer.")
    except ValueError as ve:
        print(f"Invalid input: {ve}")
        sys.exit(1)

    # 2. Establish Connection (Using Windows Authentication)
    
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # 3. Read the Excel file as binary
        with open(file_path, 'rb') as f:
            original_binary  = f.read()

        # 4. Execute the update using a CTE for row numbers
        # Replace 'SomeColumn' with the column you want to sort by

        update_sql = f"UPDATE _submissiontype SET template_file = ? WHERE id = ?;"
        cursor.execute(update_sql, (pyodbc.Binary(original_binary), row_number))
        conn.commit()
        print(f"Uploaded file to database for ID {row_number}. Running check...")
        # 5. Verify the SAME specific ID
        verify_sql = f"SELECT template_file FROM _submissiontype WHERE id = ?;"
        cursor.execute(verify_sql, (row_number,))
        result = cursor.fetchone()

        if result:
            db_binary = result[0]
            if db_binary == original_binary:
                print("✅ SUCCESS: Matches exactly.")
            else:
                # If sizes differ, the column might be the wrong data type (e.g. VARBINARY(100) instead of MAX)
                print(f"❌ FAILURE: Size mismatch. Local: {len(original_binary)}, DB: {len(db_binary)}")


    except Exception as e:
        print(f"Error: {e}")

    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
