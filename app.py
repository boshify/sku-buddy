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
            df = pd.read_csv(file, delimiter=delimiter, on_bad_lines='skip', engine='c', encoding='utf-8')
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
    df.columns = df.columns.str.strip()  # Strip whitespace from column names
    cols = pd.Series(df.columns)
    for idx in range(len(cols)):
        if not cols[idx] or pd.isna(cols[idx]):
            cols[idx] = f"Unnamed_{idx}"
    for dup in cols[cols.duplicated()].unique():
        count = 1
        for idx in cols[cols == dup].index:
            if count == 1:
                count += 1
                continue
            cols[idx] = f"{dup}_{count}"
            count += 1
    df.columns = cols
    df = df.loc[:, ~df.columns.duplicated()]  # Remove any remaining duplicate columns
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
