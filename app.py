import streamlit as st
import pandas as pd
import requests
from io import BytesIO
from lxml import etree
from requests.auth import HTTPBasicAuth
import csv

# Helper function to load and process CSV, XLS, or XML files
def load_file(file, file_type, delimiter=None):
    try:
        if file_type == "csv":
            if delimiter is None:
                # Automatically detect delimiter if not provided
                sample = file.read(1024).decode(errors='replace')
                sniffer = csv.Sniffer()
                try:
                    delimiter = sniffer.sniff(sample).delimiter
                except csv.Error:
                    delimiter = ','  # Default to comma if detection fails
                file.seek(0)
            df = pd.read_csv(file, delimiter=delimiter, on_bad_lines='skip', engine='python', encoding='utf-8')
            df = rename_duplicate_columns(df)
            return df
        elif file_type == "xlsx":
            df = pd.read_excel(file, engine='openpyxl')
            df = rename_duplicate_columns(df)
            return df
        elif file_type == "xml":
            tree = etree.parse(BytesIO(file.read()))
            products = tree.findall('.//product')
            data = []
            for p in products:
                sku = p.findtext('.//product_sku')
                product_name = p.findtext('.//product_name')
                price = p.findtext('.//price')
                if sku is not None and product_name is not None and price is not None:
                    data.append([sku.strip() if sku else None, product_name.strip() if product_name else None, price.strip() if price else None])
            df = pd.DataFrame(data, columns=['SKU', 'Product_Name', 'Price'])
            df = rename_duplicate_columns(df)
            return df
    except pd.errors.ParserError as e:
        st.error(f"Error loading file: {e}. This may be due to an issue with file formatting. Please check your CSV file for formatting errors.")
        return None
    except Exception as e:
        st.error(f"Failed to process file: {e}")
        return None

# Function to rename duplicate columns by appending suffixes
def rename_duplicate_columns(df):
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        count = 1
        for idx in cols[cols == dup].index:
            if count == 1:
                count += 1
                continue
            cols[idx] = f"{dup}_{count}"
            count += 1
    df.columns = cols
    return df

# Streamlit App Layout
st.title("Product Feed SKU Matcher")

# Step 1: Upload Master File
st.header("Step 1: Upload Master Product Feed")
master_file = st.file_uploader("Upload Master Product Feed (CSV, XLS, XML)", type=["csv", "xlsx", "xml"])

if master_file:
    file_type = master_file.name.split(".")[-1]
    master_df = load_file(master_file, file_type)
    if master_df is not None:
        master_df.columns = master_df.columns.str.strip().str.lower()
        st.success(f"Master file '{master_file.name}' loaded successfully!")
        st.write("Master File Preview:", master_df.head())
        st.write("Master File Columns:", list(master_df.columns))  # Display all column names for debugging
        st.session_state['master_df'] = master_df

        # Ask for SKU field and Match Key field in the master file
        sku_name_master = st.selectbox("Select SKU Column from Master File", master_df.columns)
        match_key_master = st.selectbox("Select Match Key Column from Master File", master_df.columns)
        st.session_state['sku_name_master'] = sku_name_master
        st.session_state['match_key_master'] = match_key_master

# Step 2: Upload Supplier File
st.header("Step 2: Upload Supplier File or Provide URL")
supplier_source = st.selectbox("Select Supplier File Source", ["Upload from Computer", "From URL"])

supplier_df = None

if supplier_source == "Upload from Computer":
    supplier_file = st.file_uploader("Upload Supplier File (CSV, XLS, XML)", type=["csv", "xlsx", "xml"])

    if supplier_file:
        file_type = supplier_file.name.split(".")[-1]
        supplier_df = load_file(supplier_file, file_type, delimiter=None)
        if supplier_df is not None:
            supplier_df.columns = supplier_df.columns.str.strip().str.lower()
            st.success(f"Supplier file '{supplier_file.name}' loaded successfully!")
            st.write("Supplier File Preview:", supplier_df.head())
            st.write("Supplier File Columns:", list(supplier_df.columns))  # Display all column names for debugging
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

            # Check response status
            if response.status_code != 200:
                st.error(f"Failed to fetch file from URL. HTTP Status Code: {response.status_code}")
            else:
                # Check file type and load the file
                file_type = supplier_url.split(".")[-1]
                supplier_df = load_file(BytesIO(response.content), file_type, delimiter=None)
                if supplier_df is not None:
                    supplier_df.columns = supplier_df.columns.str.strip().str.lower()
                    st.success(f"Supplier file from URL '{supplier_url}' loaded successfully!")
                    st.write("Supplier File Preview:", supplier_df.head())
                    st.write("Supplier File Columns:", list(supplier_df.columns))  # Display all column names for debugging
                    st.session_state['supplier_df'] = supplier_df

        except Exception as e:
            st.error(f"Failed to load file from URL: {e}")

# Step 3: Set Supplier SKU and Match Key
if 'supplier_df' in st.session_state:
    st.header("Step 3: Select Supplier SKU and Match Key Fields")
    
    supplier_df = st.session_state['supplier_df']
    
    sku_name_supplier = st.selectbox("Select SKU Column from Supplier File", supplier_df.columns)
    match_key_supplier = st.selectbox("Select Match Key Column from Supplier File", supplier_df.columns)
    st.session_state['sku_name_supplier'] = sku_name_supplier
    st.session_state['match_key_supplier'] = match_key_supplier

# Step 4: Process Matching
if 'master_df' in st.session_state and 'supplier_df' in st.session_state:
    st.header("Step 4: Match Products and Update SKUs")

    if st.button("Match Products and Update SKUs") or 'matched_df' not in st.session_state:
        master_df = st.session_state['master_df']
        supplier_df = st.session_state['supplier_df']
        sku_name_master = st.session_state['sku_name_master']
        match_key_master = st.session_state['match_key_master']
        sku_name_supplier = st.session_state['sku_name_supplier']
        match_key_supplier = st.session_state['match_key_supplier']

        # Ensure all match keys are treated as strings to avoid mismatches due to type differences
        try:
            if match_key_master not in master_df.columns or match_key_supplier not in supplier_df.columns:
                st.error("Selected Match Key columns do not exist in the respective DataFrames. Please select valid columns.")
                st.stop()

            if sku_name_master not in master_df.columns or sku_name_supplier not in supplier_df.columns:
                st.error("Selected SKU columns do not exist in the respective DataFrames. Please select valid columns.")
                st.stop()

            master_df[match_key_master] = master_df[match_key_master].fillna('').astype(str).str.strip().str.lower()
            supplier_df[match_key_supplier] = supplier_df[match_key_supplier].fillna('').astype(str).str.strip().str.lower()

            # Ensure the SKU columns are also treated as strings
            master_df[sku_name_master] = master_df[sku_name_master].fillna('').astype(str).str.strip()
            supplier_df[sku_name_supplier] = supplier_df[sku_name_supplier].fillna('').astype(str).str.strip()
        except KeyError as e:
            st.error(f"A KeyError occurred while converting columns to string: {e}. Please make sure the selected columns exist.")
            st.stop()

        # Proceed with matching using column names directly
        try:
            # Rename columns for merge to prevent conflicts
            master_df_renamed = rename_duplicate_columns(master_df.rename(columns={
                match_key_master: 'match_key',
                sku_name_master: 'master_sku'
            }))
            supplier_df_renamed = rename_duplicate_columns(supplier_df.rename(columns={
                match_key_supplier: 'match_key',
                sku_name_supplier: 'supplier_sku'
            }))

            matched_df = pd.merge(
                master_df_renamed, 
                supplier_df_renamed, 
                on='match_key', 
                how='inner'
            )
            st.session_state['matched_df'] = matched_df

            # Display rows with mismatched SKUs
            sku_mismatch_df = matched_df[matched_df['master_sku'] != matched_df['supplier_sku']]
            if not sku_mismatch_df.empty:
                st.write("Rows with mismatched SKUs:", sku_mismatch_df[['match_key', 'master_sku', 'supplier_sku']])
                st.session_state['sku_mismatch_df'] = sku_mismatch_df

        except KeyError as e:
            st.error(f"A KeyError occurred during the merge: {e}. Please make sure the selected columns exist and have matching values.")
            st.stop()

    # Provide an option to overwrite Master SKUs with Supplier SKUs where mismatched
    if 'sku_mismatch_df' in st.session_state and st.button("Overwrite Master SKUs with Supplier SKUs where mismatched"):
        updated_df = st.session_state['master_df'].copy()
        sku_mismatch_df = st.session_state['sku_mismatch_df'].drop_duplicates(subset='match_key')
        updated_df.loc[updated_df[st.session_state['match_key_master']].isin(sku_mismatch_df['match_key']), st.session_state['sku_name_master']] = updated_df[st.session_state['match_key_master']].map(sku_mismatch_df.set_index('match_key')['supplier_sku'])
        st.session_state['updated_df'] = updated_df
        st.session_state['skus_updated'] = len(sku_mismatch_df)

        # Find products from supplier that are not in master
        unmatched_df = st.session_state['supplier_df'][~st.session_state['supplier_df'][st.session_state['match_key_supplier']].isin(st.session_state['matched_df']['match_key'])]
        st.session_state['unmatched_df'] = unmatched_df
        st.session_state['products_not_in_master'] = len(unmatched_df)

        # Display success message with summary
        st.success(f"SKUs Updated: {st.session_state['skus_updated']}. Products Not In Master: {st.session_state['products_not_in_master']}")

# Step 5: Provide Downloadable Files if Available
if 'updated_df' in st.session_state and 'unmatched_df' in st.session_state:
    st.header("Step 5: Download Updated Files")

    updated_df = st.session_state['updated_df']
    unmatched_df = st.session_state['unmatched_df']

    # Download updated master file with new SKUs
    updated_csv = updated_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Master with Updated SKUs", updated_csv, "updated_master.csv", "text/csv")

    # Download supplier products not found in the master
    unmatched_csv = unmatched_df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Products from Supplier Not Found in Master", unmatched_csv, "unmatched_products.csv", "text/csv")
