import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from lxml import etree
from requests.auth import HTTPBasicAuth

# Helper function to ensure columns consistency
def ensure_columns(df, columns):
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]

# Helper function to load and process CSV, XLS, or XML files
def load_file(file, file_type, delimiter=','):
    try:
        if file_type == "csv":
            # Use on_bad_lines='skip' to skip problematic lines in recent pandas versions
            return pd.read_csv(file, delimiter=delimiter, on_bad_lines='skip')
        elif file_type == "xlsx":
            return pd.read_excel(file, engine='openpyxl')
        elif file_type == "xml":
            tree = etree.parse(file)
            products = tree.xpath('//product')
            data = [[p.findtext('SKU'), p.findtext('Product_Name'), p.findtext('Price')] for p in products]
            return pd.DataFrame(data, columns=['SKU', 'Product_Name', 'Price'])
    except pd.errors.ParserError as e:
        st.error(f"Error loading file: {e}. This may be due to an issue with file formatting. Please check your CSV file for formatting errors.")
        return None
    except Exception as e:
        st.error(f"Failed to process file: {e}")
        return None

# Streamlit App Layout
st.title("Product Feed SKU Matcher")

# Upload Master File
st.header("Step 1: Upload Master Product Feed")
master_file = st.file_uploader("Upload Master Product Feed (CSV, XLS, XML)", type=["csv", "xlsx", "xml"])

if master_file:
    file_type = master_file.name.split(".")[-1]
    master_df = load_file(master_file, file_type)
    if master_df is not None:
        st.success(f"Master file '{master_file.name}' loaded successfully!")
        st.write("Master File Preview:", master_df.head())
        st.session_state['master_df'] = master_df

        # Allow the user to specify the SKU column in the master file
        sku_name_master = st.selectbox("Select SKU Name Column from Master File", master_df.columns)
        st.session_state['sku_name_master'] = sku_name_master

# Step 2: Upload Supplier File
st.header("Step 2: Upload Supplier File or Provide URL")
supplier_source = st.selectbox("Select Supplier File Source", ["Upload from Computer", "From URL"])

supplier_df = None

if supplier_source == "Upload from Computer":
    supplier_file = st.file_uploader("Upload Supplier File (CSV, XLS, XML)", type=["csv", "xlsx", "xml"])

    if supplier_file:
        file_type = supplier_file.name.split(".")[-1]
        supplier_df = load_file(supplier_file, file_type)
        if supplier_df is not None:
            st.success(f"Supplier file '{supplier_file.name}' loaded successfully!")
            st.write("Supplier File Preview:", supplier_df.head())
            st.session_state['supplier_df'] = supplier_df

elif supplier_source == "From URL":
    supplier_url = st.text_input("Enter Supplier File URL")
    username = st.text_input("Username (Optional)", value="")
    password = st.text_input("Password (Optional)", type="password", value="")

    if supplier_url:
        try:
            # If username or password is blank, do not use authentication
            if username and password:
                response = requests.get(supplier_url, auth=HTTPBasicAuth(username, password))
            else:
                response = requests.get(supplier_url)

            # Check file type and load the file
            file_type = supplier_url.split(".")[-1]
            supplier_df = load_file(BytesIO(response.content), file_type, delimiter=';')  # Explicitly setting semicolon as delimiter
            if supplier_df is not None:
                st.success(f"Supplier file from URL '{supplier_url}' loaded successfully!")
                st.write("Supplier File Preview:", supplier_df.head())
                st.session_state['supplier_df'] = supplier_df

        except Exception as e:
            st.error(f"Failed to load file from URL: {e}")

# Step 3: Set Matching and Mapping Attributes
if 'master_df' in st.session_state and 'supplier_df' in st.session_state:
    st.header("Step 3: Select Matching and Mapping Attributes")
    
    master_df = st.session_state['master_df']
    supplier_df = st.session_state['supplier_df']
    sku_name_master = st.session_state['sku_name_master']
    
    match_key = st.selectbox("Select Match Key Attribute from Master File", master_df.columns)
    file_mapping_key = st.selectbox("Select File Mapping Attribute from Supplier File", supplier_df.columns)

    # Step 4: Process Matching
    if st.button("Match Products and Update SKUs"):
        # Find products that match in both files based on the selected key
        matched_df = pd.merge(master_df, supplier_df, left_on=match_key, right_on=file_mapping_key, how='inner', suffixes=('_master', '_supplier'))

        # Check if SKUs are different and update
        updated_df = master_df.copy()
        for index, row in matched_df.iterrows():
            if row[sku_name_master] != row['SKU_supplier']:
                updated_df.loc[updated_df[match_key] == row[match_key], sku_name_master] = row['SKU_supplier']

        # Find products from supplier that are not in master
        unmatched_df = supplier_df[~supplier_df[file_mapping_key].isin(matched_df[file_mapping_key])]

        # Step 5: Provide Downloadable Files
        st.header("Step 4: Download Updated Files")

        # Download updated master file with new SKUs
        updated_csv = updated_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Master with Updated SKUs", updated_csv, "updated_master.csv", "text/csv")

        # Download supplier products not found in the master
        unmatched_csv = unmatched_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Products from Supplier Not Found in Master", unmatched_csv, "unmatched_products.csv", "text/csv")

        st.success("Files are ready for download!")
