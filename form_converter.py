import streamlit as st
import pandas as pd
import numpy as np
import re
import io
import os
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# Set page config
st.set_page_config(
    page_title="SurveyCTO to Kobo XLSForm Converter",
    page_icon="📊",
    layout="wide"
)

# Initialize session state
if 'current_step' not in st.session_state:
    st.session_state.current_step = 0

if 'survey_df' not in st.session_state:
    st.session_state.survey_df = None

if 'choices_df' not in st.session_state:
    st.session_state.choices_df = None

if 'settings_df' not in st.session_state:
    st.session_state.settings_df = None

if 'form_name' not in st.session_state:
    st.session_state.form_name = ""

if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None

if 'edited_dfs' not in st.session_state:
    st.session_state.edited_dfs = {}

# App title and description
st.title("SurveyCTO to Kobo XLSForm Converter")
st.markdown("""
This app converts SurveyCTO XLS forms to Kobo-compatible XLSForms following a standardized pipeline.
You can navigate through each step of the conversion process, view and edit the data at each step.
""")

# Define all steps
STEPS = [
    "Upload File",
    "Load Core Sheets",
    "Normalize Language Columns",
    "Fix Field Types",
    "Apply Label Fallbacks",
    "Clean Calculation Fields",
    "Remove Invalid Defaults",
    "Normalize Field Names",
    "Validate Group & Repeat Logic",
    "Fix Cascading Selects",
    "Check Settings Sheet",
    "Remove Redundant Columns",
    "Export File"
]

# Sidebar with step information
with st.sidebar:
    st.header("Conversion Steps")
    
    # Show all steps with the current one highlighted
    for i, step in enumerate(STEPS):
        if i == st.session_state.current_step:
            st.markdown(f"**→ {i+1}. {step}**")
        else:
            st.markdown(f"{i+1}. {step}")
    
    st.markdown("---")
    st.info("Navigate through each step to see and edit the changes before exporting the final file.")
    st.markdown("---")
    st.caption("🔧 Made with ❤️ by ***MK***")
    st.caption("✉️ muhammad.kh92@gmail.com")

# Utility functions
def is_empty(value):
    if isinstance(value, float) and np.isnan(value):
        return True
    if value is None or value == "" or pd.isna(value):
        return True
    return False

def normalize_name(name):
    if is_empty(name):
        return ""
    
    # Convert to string if not already
    name = str(name)
    
    # Convert to lowercase
    name = name.lower()
    
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    
    # Remove invalid characters (keep only a-z, 0-9, _)
    name = re.sub(r'[^a-z0-9_]', '', name)
    
    return name

def ensure_unique_names(df, name_col='name'):
    names = {}
    new_names = []
    
    for index, name in enumerate(df[name_col]):
        if is_empty(name):
            new_names.append(name)
            continue
            
        normalized_name = normalize_name(name)
        
        if normalized_name in names:
            counter = names[normalized_name] + 1
            names[normalized_name] = counter
            new_names.append(f"{normalized_name}_{counter}")
        else:
            names[normalized_name] = 0
            new_names.append(normalized_name)
    
    df[name_col] = new_names
    return df

def normalize_language_columns(df):
    # Get all columns
    columns = df.columns.tolist()
    
    # Define mapping patterns
    label_english_patterns = [
        'label', 'label:English', 'label::English (en)', 'label::English'
    ]
    
    label_arabic_patterns = [
        'label:العربية', 'label::Arabic (ar)', 'label::العربية', 'label::Arabic'
    ]
    
    hint_english_patterns = [
        'hint', 'hint:English', 'hint::English (en)', 'hint::English'
    ]
    
    hint_arabic_patterns = [
        'hint:العربية', 'hint::Arabic (ar)', 'hint::العربية', 'hint::Arabic'
    ]
    
    # Create standardized columns if they don't exist
    if 'label::English' not in df.columns:
        df['label::English'] = ''
    
    if 'label::Arabic' not in df.columns:
        df['label::Arabic'] = ''
    
    if 'hint::English' not in df.columns:
        df['hint::English'] = ''
    
    if 'hint::Arabic' not in df.columns:
        df['hint::Arabic'] = ''
    
    # Map existing columns to standardized ones
    for col in columns:
        # Handle label::English
        if col in label_english_patterns and col != 'label::English':
            df['label::English'] = df.apply(
                lambda row: row[col] if is_empty(row['label::English']) and not is_empty(row[col]) else row['label::English'], 
                axis=1
            )
        
        # Handle label::Arabic
        elif col in label_arabic_patterns and col != 'label::Arabic':
            df['label::Arabic'] = df.apply(
                lambda row: row[col] if is_empty(row['label::Arabic']) and not is_empty(row[col]) else row['label::Arabic'], 
                axis=1
            )
        
        # Handle hint::English
        elif col in hint_english_patterns and col != 'hint::English':
            df['hint::English'] = df.apply(
                lambda row: row[col] if is_empty(row['hint::English']) and not is_empty(row[col]) else row['hint::English'], 
                axis=1
            )
        
        # Handle hint::Arabic
        elif col in hint_arabic_patterns and col != 'hint::Arabic':
            df['hint::Arabic'] = df.apply(
                lambda row: row[col] if is_empty(row['hint::Arabic']) and not is_empty(row[col]) else row['hint::Arabic'], 
                axis=1
            )
    
    # Remove other label columns
    columns_to_drop = []
    for col in columns:
        if (col.startswith('label:') or col.startswith('label::')) and col not in ['label::English', 'label::Arabic']:
            columns_to_drop.append(col)
        elif (col.startswith('hint:') or col.startswith('hint::')) and col not in ['hint::English', 'hint::Arabic']:
            columns_to_drop.append(col)
    
    # Drop columns
    df = df.drop(columns=columns_to_drop, errors='ignore')
    
    return df

def fix_field_types(df):
    # Unsupported field types to convert to text
    unsupported_types = [
        'deviceid', 'username', 'subscriberid', 'simserial',
        'phonenumber', 'caseid', 'text audit', 'comments', 'audit'
    ]
    
    # Standard KoBo field types
    standard_types = [
        'text', 'integer', 'decimal', 'select_one', 'select_multiple',
        'note', 'geopoint', 'geotrace', 'geoshape', 'date', 'time',
        'dateTime', 'image', 'audio', 'video', 'file', 'barcode',
        'calculate', 'acknowledge', 'hidden', 'xml-external',
        'begin group', 'end group', 'begin repeat', 'end repeat'
    ]
    
    # Function to check if a type is standard
    def is_standard_type(type_val):
        if is_empty(type_val):
            return False
        
        type_str = str(type_val).strip()
        
        # Check exact matches
        if type_str in standard_types:
            return True
        
        # Check for select_one with list name
        if type_str.startswith('select_one '):
            return True
        
        # Check for select_multiple with list name
        if type_str.startswith('select_multiple '):
            return True
        
        return False
    
    # Convert types
    for idx, row in df.iterrows():
        if 'type' in df.columns and not is_empty(row['type']):
            type_val = str(row['type']).strip()
            
            # Convert unsupported types to text
            if type_val in unsupported_types:
                df.at[idx, 'type'] = 'text'
            
            # Handle select_one special cases
            elif type_val.startswith('select_one '):
                # Fix cascading select issues
                if 'sGovernorate' in type_val:
                    df.at[idx, 'type'] = 'select_one governorate'
                elif 'sDistrict' in type_val:
                    df.at[idx, 'type'] = 'select_one district'
                elif 'sSubdistrict' in type_val:
                    df.at[idx, 'type'] = 'select_one subdistrict'
            
            # Convert non-standard types to text
            elif not is_standard_type(type_val):
                df.at[idx, 'type'] = 'text'
    
    return df

def apply_fallbacks(df):
    # Ensure the name column exists
    if 'name' not in df.columns:
        return df
    
    # Apply fallbacks for each row
    for idx, row in df.iterrows():
        name = row['name']
        if is_empty(name):
            continue
        
        # Apply fallbacks for label::English
        if 'label::English' in df.columns and is_empty(row['label::English']):
            df.at[idx, 'label::English'] = f"Input for {name}"
        
        # Apply fallbacks for label::Arabic
        if 'label::Arabic' in df.columns and is_empty(row['label::Arabic']):
            df.at[idx, 'label::Arabic'] = f"إدخال لـ {name}"
        
        # Apply fallbacks for hint::English
        if 'hint::English' in df.columns and is_empty(row['hint::English']):
            df.at[idx, 'hint::English'] = f"Hint for {name}"
        
        # Apply fallbacks for hint::Arabic
        if 'hint::Arabic' in df.columns and is_empty(row['hint::Arabic']):
            df.at[idx, 'hint::Arabic'] = f"تلميح لـ {name}"
    
    return df

def has_invalid_expression(value):
    if is_empty(value):
        return False
    
    value_str = str(value)
    
    # Check for common invalid patterns
    invalid_patterns = [
        'pulldata(',
        'duration(',
        'if(<', 'if(=', 'if(,)',
        'selected(,)',
        '(+())', '(*1)', '(*2)',
        '${'
    ]
    
    for pattern in invalid_patterns:
        if pattern in value_str:
            return True
    
    return False

def clean_calculation_fields(df):
    # Columns to check for invalid expressions
    check_cols = ['calculation', 'required', 'relevant', 'constraint', 'choice_filter']
    
    # Iterate through rows
    for idx, row in df.iterrows():
        should_convert = False
        
        # Check each column for invalid expressions
        for col in check_cols:
            if col in df.columns and not is_empty(row.get(col)) and has_invalid_expression(row[col]):
                should_convert = True
                break
        
        # Convert to text and clear calculation if needed
        if should_convert and 'type' in df.columns:
            df.at[idx, 'type'] = 'text'
            
            if 'calculation' in df.columns:
                df.at[idx, 'calculation'] = ''
    
    return df

def clean_default_values(df):
    if 'default' not in df.columns:
        return df
    
    for idx, row in df.iterrows():
        default_val = row.get('default')
        
        if not is_empty(default_val):
            default_str = str(default_val)
            
            # Check for expressions
            if 'pulldata(' in default_str or '${' in default_str:
                df.at[idx, 'default'] = ''
    
    return df

def validate_group_repeat_logic(df):
    if 'type' not in df.columns:
        return df
    
    # Count begin/end tags
    begin_group_count = 0
    begin_repeat_count = 0
    
    # Track positions where we might need to add closing tags
    missing_end_groups = []
    missing_end_repeats = []
    
    # First pass: count and track
    for idx, row in df.iterrows():
        type_val = row.get('type')
        
        if is_empty(type_val):
            continue
        
        type_str = str(type_val).strip()
        
        if type_str == 'begin group':
            begin_group_count += 1
            missing_end_groups.append(idx)
        elif type_str == 'end group':
            begin_group_count -= 1
            if missing_end_groups:
                missing_end_groups.pop()
        elif type_str == 'begin repeat':
            begin_repeat_count += 1
            missing_end_repeats.append(idx)
        elif type_str == 'end repeat':
            begin_repeat_count -= 1
            if missing_end_repeats:
                missing_end_repeats.pop()
    
    # Second pass: add missing closing tags if needed
    new_rows = []
    
    # First close repeats, then groups
    for idx in reversed(missing_end_repeats):
        # Create a new row with end repeat
        new_row = {col: '' for col in df.columns}
        new_row['type'] = 'end repeat'
        new_rows.append((df.index[-1] + 1 + len(new_rows), new_row))
    
    for idx in reversed(missing_end_groups):
        # Create a new row with end group
        new_row = {col: '' for col in df.columns}
        new_row['type'] = 'end group'
        new_rows.append((df.index[-1] + 1 + len(new_rows), new_row))
    
    # Add new rows to the dataframe
    for idx, new_row in new_rows:
        df.loc[idx] = new_row
    
    # Sort by index and reset
    df = df.sort_index().reset_index(drop=True)
    
    return df

def create_standard_location_choices():
    # This is a simplified example - in a real application, you would load 
    # this data from a predefined template or database
    governorate_data = [
        {"list_name": "governorate", "name": "baghdad", "label::English": "Baghdad", "label::Arabic": "بغداد"},
        {"list_name": "governorate", "name": "basra", "label::English": "Basra", "label::Arabic": "البصرة"},
        {"list_name": "governorate", "name": "erbil", "label::English": "Erbil", "label::Arabic": "أربيل"}
    ]
    
    district_data = [
        {"list_name": "district", "name": "district1", "label::English": "District 1", "label::Arabic": "المنطقة 1", "governorate": "baghdad"},
        {"list_name": "district", "name": "district2", "label::English": "District 2", "label::Arabic": "المنطقة 2", "governorate": "baghdad"},
        {"list_name": "district", "name": "district3", "label::English": "District 3", "label::Arabic": "المنطقة 3", "governorate": "basra"}
    ]
    
    subdistrict_data = [
        {"list_name": "subdistrict", "name": "subdistrict1", "label::English": "Subdistrict 1", "label::Arabic": "الناحية 1", "district": "district1"},
        {"list_name": "subdistrict", "name": "subdistrict2", "label::English": "Subdistrict 2", "label::Arabic": "الناحية 2", "district": "district1"},
        {"list_name": "subdistrict", "name": "subdistrict3", "label::English": "Subdistrict 3", "label::Arabic": "الناحية 3", "district": "district2"}
    ]
    
    # Combine all data
    all_data = governorate_data + district_data + subdistrict_data
    
    return pd.DataFrame(all_data)

def fix_cascading_selects(choices_df):
    if choices_df is None or len(choices_df) == 0:
        return create_standard_location_choices()
    
    # Create standard location choices
    standard_locations = create_standard_location_choices()
    
    # Remove existing location choices
    choices_df = choices_df[~choices_df['list_name'].isin(['governorate', 'district', 'subdistrict'])]
    
    # Append standard locations
    choices_df = pd.concat([choices_df, standard_locations], ignore_index=True)
    
    return choices_df

def fix_settings_sheet(settings_df, form_name):
    if settings_df is None or len(settings_df) == 0:
        # Create a basic settings sheet
        settings_df = pd.DataFrame({
            'form_title': [form_name],
            'form_id': [normalize_name(form_name)],
            'default_language': ['English']
        })
    else:
        # Ensure required fields exist
        if 'form_title' not in settings_df.columns or is_empty(settings_df['form_title'].iloc[0]):
            settings_df['form_title'] = form_name
        
        if 'form_id' not in settings_df.columns or is_empty(settings_df['form_id'].iloc[0]):
            settings_df['form_id'] = normalize_name(form_name)
        
        # Set default language
        settings_df['default_language'] = 'English'
    
    return settings_df

def remove_redundant_columns(df):
    # Drop empty columns
    df = df.dropna(axis=1, how='all')
    
    # List of unused advanced columns to drop
    unused_columns = ['style', 'readonly', 'publishable', 'autoplay']
    
    # Drop unused columns if they exist
    df = df.drop(columns=[col for col in unused_columns if col in df.columns], errors='ignore')
    
    return df

def create_excel_file(survey_df, choices_df, settings_df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        survey_df.to_excel(writer, sheet_name='survey', index=False)
        if choices_df is not None:
            choices_df.to_excel(writer, sheet_name='choices', index=False)
        settings_df.to_excel(writer, sheet_name='settings', index=False)
    
    output.seek(0)
    return output

# Navigation functions
def go_next():
    if st.session_state.current_step < len(STEPS) - 1:
        st.session_state.current_step += 1

def go_back():
    if st.session_state.current_step > 0:
        st.session_state.current_step -= 1

def go_to_step(step):
    st.session_state.current_step = step

# Step function implementations
def step_upload_file():
    st.header("Step 1: Upload SurveyCTO XLS Form")
    
    uploaded_file = st.file_uploader("Upload SurveyCTO XLS Form", type=['xls', 'xlsx'])
    
    if uploaded_file is not None:
        file_name = uploaded_file.name
        form_name = os.path.splitext(file_name)[0]
        
        st.success(f"File uploaded: {file_name}")
        
        if st.button("Proceed to Next Step"):
            st.session_state.uploaded_file = uploaded_file
            st.session_state.form_name = form_name
            go_next()
            st.rerun()
    else:
        st.info("Please upload a SurveyCTO XLS Form to proceed.")

def step_load_core_sheets():
    st.header("Step 2: Load Core Sheets")
    
    if st.session_state.uploaded_file is None:
        st.error("No file uploaded. Please go back to step 1.")
        return
    
    try:
        # Load the Excel file
        xls = pd.ExcelFile(st.session_state.uploaded_file)
        
        # Get the sheets
        sheet_names = xls.sheet_names
        
        # Check for required sheets
        required_sheets = ['survey', 'choices', 'settings']
        missing_sheets = [sheet for sheet in required_sheets if sheet not in sheet_names]
        
        if missing_sheets:
            st.warning(f"Missing sheets: {', '.join(missing_sheets)}. Some will be created automatically.")
        
        # Load survey sheet
        if 'survey' in sheet_names:
            survey_df = pd.read_excel(xls, 'survey')
            survey_df = survey_df.dropna(how='all')
            st.session_state.survey_df = survey_df
            st.success("Survey sheet loaded successfully.")
        else:
            st.error("Survey sheet is required but missing.")
            return
        
        # Load choices sheet
        if 'choices' in sheet_names:
            choices_df = pd.read_excel(xls, 'choices')
            choices_df = choices_df.dropna(how='all')
            st.session_state.choices_df = choices_df
            st.success("Choices sheet loaded successfully.")
        else:
            st.session_state.choices_df = pd.DataFrame(columns=['list_name', 'name', 'label'])
            st.info("Choices sheet not found. Created an empty one.")
        
        # Load settings sheet
        if 'settings' in sheet_names:
            settings_df = pd.read_excel(xls, 'settings')
            settings_df = settings_df.dropna(how='all')
            st.session_state.settings_df = settings_df
            st.success("Settings sheet loaded successfully.")
        else:
            st.session_state.settings_df = pd.DataFrame({
                'form_title': [st.session_state.form_name],
                'form_id': [normalize_name(st.session_state.form_name)],
                'default_language': ['English']
            })
            st.info("Settings sheet not found. Created a basic one.")
        
        # Preprocess dataframes to handle potential issues
        def safe_df_for_editor(df):
            if df is None:
                return None
            # Replace any problematic values
            df = df.fillna("")  # Fill NaN values with empty strings
            # Convert all columns to string type to avoid type issues
            for col in df.columns:
                df[col] = df[col].astype(str)
            return df
        
        # Create safe versions of the dataframes for editing
        safe_survey_df = safe_df_for_editor(st.session_state.survey_df)
        safe_choices_df = safe_df_for_editor(st.session_state.choices_df) if st.session_state.choices_df is not None else None
        safe_settings_df = safe_df_for_editor(st.session_state.settings_df) if st.session_state.settings_df is not None else None
        
        # Display the loaded sheets
        st.subheader("Survey Sheet")
        try:
            with st.expander("View and Edit Survey Sheet", expanded=True):
                st.markdown("**Note:** This is a paginated view. You can edit cells directly.")
                edited_survey_df = st.data_editor(
                    safe_survey_df,
                    use_container_width=True,
                    height=300
                )
                st.session_state.edited_dfs['survey'] = edited_survey_df
        except Exception as e:
            st.error(f"Error displaying survey data editor: {str(e)}")
            st.warning("Displaying as read-only dataframe instead")
            st.dataframe(safe_survey_df, use_container_width=True)
        
        st.subheader("Choices Sheet")
        if safe_choices_df is not None:
            try:
                with st.expander("View and Edit Choices Sheet", expanded=True):
                    st.markdown("**Note:** This is a paginated view. You can edit cells directly.")
                    edited_choices_df = st.data_editor(
                        safe_choices_df,
                        use_container_width=True,
                        height=300
                    )
                    st.session_state.edited_dfs['choices'] = edited_choices_df
            except Exception as e:
                st.error(f"Error displaying choices data editor: {str(e)}")
                st.warning("Displaying as read-only dataframe instead")
                st.dataframe(safe_choices_df, use_container_width=True)
        
        st.subheader("Settings Sheet")
        if safe_settings_df is not None:
            try:
                with st.expander("View and Edit Settings Sheet", expanded=True):
                    st.markdown("**Note:** This is a paginated view. You can edit cells directly.")
                    edited_settings_df = st.data_editor(
                        safe_settings_df,
                        use_container_width=True,
                        height=200
                    )
                    st.session_state.edited_dfs['settings'] = edited_settings_df
            except Exception as e:
                st.error(f"Error displaying settings data editor: {str(e)}")
                st.warning("Displaying as read-only dataframe instead")
                st.dataframe(safe_settings_df, use_container_width=True)
        
        # Navigation buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back"):
                st.session_state.survey_df = None
                st.session_state.choices_df = None
                st.session_state.settings_df = None
                go_back()
                st.rerun()
        with col2:
            if st.button("Next →"):
                # Update dataframes with edited versions if available
                if 'survey' in st.session_state.edited_dfs:
                    st.session_state.survey_df = st.session_state.edited_dfs['survey']
                if 'choices' in st.session_state.edited_dfs:
                    st.session_state.choices_df = st.session_state.edited_dfs['choices']
                if 'settings' in st.session_state.edited_dfs:
                    st.session_state.settings_df = st.session_state.edited_dfs['settings']
                go_next()
                st.rerun()
    
    except Exception as e:
        st.error(f"Error loading sheets: {str(e)}")

def step_normalize_language_columns():
    st.header("Step 3: Normalize Language Columns")
    
    if st.session_state.survey_df is None:
        st.error("No survey data loaded. Please go back to step 2.")
        return
    
    # Display the before state
    st.subheader("Before Normalization")
    with st.expander("View Original Survey Sheet", expanded=False):
        st.dataframe(st.session_state.survey_df, use_container_width=True)
    
    if st.session_state.choices_df is not None:
        with st.expander("View Original Choices Sheet", expanded=False):
            st.dataframe(st.session_state.choices_df, use_container_width=True)
    
    # Apply normalization
    if 'language_normalized' not in st.session_state:
        st.session_state.normalized_survey_df = normalize_language_columns(st.session_state.survey_df.copy())
        
        if st.session_state.choices_df is not None:
            st.session_state.normalized_choices_df = normalize_language_columns(st.session_state.choices_df.copy())
        else:
            st.session_state.normalized_choices_df = None
        
        st.session_state.language_normalized = True
    
    # Display the after state
    st.subheader("After Normalization")
    
    st.markdown("""
    **Changes Made:**
    - Standardized all language columns to `label::English` and `label::Arabic` format
    - Merged content from various label formats into standard columns
    - Similar standardization applied to hint columns
    - Removed redundant language columns
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Normalized Survey Sheet")
    st.dataframe(st.session_state.normalized_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.normalized_survey_df)
    st.download_button(
        label="Download Survey CSV for editing",
        data=csv_survey,
        file_name="normalized_survey.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['normalized_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Display choices dataframe with download/upload options if available
    if st.session_state.normalized_choices_df is not None:
        st.subheader("Normalized Choices Sheet")
        st.dataframe(st.session_state.normalized_choices_df, use_container_width=True)
        
        csv_choices = df_to_csv(st.session_state.normalized_choices_df)
        st.download_button(
            label="Download Choices CSV for editing",
            data=csv_choices,
            file_name="normalized_choices.csv",
            mime="text/csv",
        )
        
        st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
        uploaded_choices = st.file_uploader("Upload edited Choices CSV", type=["csv"], key="choices_upload")
        if uploaded_choices is not None:
            edited_choices_df = csv_to_df(uploaded_choices)
            if edited_choices_df is not None:
                st.success("Choices CSV uploaded successfully!")
                st.session_state.edited_dfs['normalized_choices'] = edited_choices_df
                st.dataframe(edited_choices_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('language_normalized', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited versions if available
            if 'normalized_survey' in st.session_state.edited_dfs:
                st.session_state.normalized_survey_df = st.session_state.edited_dfs['normalized_survey']
            if st.session_state.normalized_choices_df is not None and 'normalized_choices' in st.session_state.edited_dfs:
                st.session_state.normalized_choices_df = st.session_state.edited_dfs['normalized_choices']
            go_next()
            st.rerun()

def step_fix_field_types():
    st.header("Step 4: Fix Field Types")
    
    if st.session_state.normalized_survey_df is None:
        st.error("No normalized survey data available. Please go back to step 3.")
        return
    
    # Display the before state
    st.subheader("Before Field Type Fixes")
    with st.expander("View Survey Sheet Before Type Fixes", expanded=False):
        st.dataframe(st.session_state.normalized_survey_df, use_container_width=True)
    
    # Apply field type fixes
    if 'field_types_fixed' not in st.session_state:
        st.session_state.fixed_survey_df = fix_field_types(st.session_state.normalized_survey_df.copy())
        st.session_state.field_types_fixed = True
    
    # Display the after state
    st.subheader("After Field Type Fixes")
    
    st.markdown("""
    **Changes Made:**
    - Converted unsupported SurveyCTO field types to Kobo-compatible `text` type
    - Fixed select_one references for cascading dropdowns
    - Standardized non-standard field types
    """)
    
    # Find and highlight the changes
    if 'type' in st.session_state.normalized_survey_df.columns and 'type' in st.session_state.fixed_survey_df.columns:
        changed_rows = []
        for idx, row in st.session_state.fixed_survey_df.iterrows():
            if idx < len(st.session_state.normalized_survey_df):
                if row['type'] != st.session_state.normalized_survey_df.iloc[idx]['type']:
                    changed_rows.append({
                        'Row': idx + 1, 
                        'Original Type': st.session_state.normalized_survey_df.iloc[idx]['type'],
                        'New Type': row['type']
                    })
        
        if changed_rows:
            st.subheader("Modified Field Types")
            st.dataframe(pd.DataFrame(changed_rows), use_container_width=True)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Type Fixes")
    st.dataframe(st.session_state.fixed_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.fixed_survey_df)
    st.download_button(
        label="Download Fixed Survey CSV for editing",
        data=csv_survey,
        file_name="fixed_survey_types.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="fixed_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['fixed_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('field_types_fixed', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'fixed_survey' in st.session_state.edited_dfs:
                st.session_state.fixed_survey_df = st.session_state.edited_dfs['fixed_survey']
            go_next()
            st.rerun()

def step_apply_label_fallbacks():
    st.header("Step 5: Apply Label and Hint Fallbacks")
    
    if st.session_state.fixed_survey_df is None:
        st.error("No fixed survey data available. Please go back to step 4.")
        return
    
    # Display the before state
    st.subheader("Before Adding Fallbacks")
    with st.expander("View Survey Sheet Before Adding Fallbacks", expanded=False):
        st.dataframe(st.session_state.fixed_survey_df, use_container_width=True)
    
    # Apply fallbacks
    if 'fallbacks_applied' not in st.session_state:
        st.session_state.fallback_survey_df = apply_fallbacks(st.session_state.fixed_survey_df.copy())
        st.session_state.fallbacks_applied = True
    
    # Display the after state
    st.subheader("After Adding Fallbacks")
    
    st.markdown("""
    **Changes Made:**
    - Added fallback English labels: `Input for {field_name}`
    - Added fallback Arabic labels: `إدخال لـ {field_name}`
    - Added similar fallbacks for hint fields
    - These ensure all fields have appropriate labels in both languages
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Adding Fallbacks")
    st.dataframe(st.session_state.fallback_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.fallback_survey_df)
    st.download_button(
        label="Download Survey with Fallbacks CSV for editing",
        data=csv_survey,
        file_name="survey_with_fallbacks.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="fallback_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['fallback_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('fallbacks_applied', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'fallback_survey' in st.session_state.edited_dfs:
                st.session_state.fallback_survey_df = st.session_state.edited_dfs['fallback_survey']
            go_next()
            st.rerun()

def step_clean_calculation_fields():
    st.header("Step 6: Clean Calculation Fields")
    
    if st.session_state.fallback_survey_df is None:
        st.error("No survey data with fallbacks available. Please go back to step 5.")
        return
    
    # Display the before state
    st.subheader("Before Cleaning Calculations")
    with st.expander("View Survey Sheet Before Cleaning Calculations", expanded=False):
        st.dataframe(st.session_state.fallback_survey_df, use_container_width=True)
    
    # Apply calculation cleaning
    if 'calculations_cleaned' not in st.session_state:
        st.session_state.calculation_survey_df = clean_calculation_fields(st.session_state.fallback_survey_df.copy())
        st.session_state.calculations_cleaned = True
    
    # Display the after state
    st.subheader("After Cleaning Calculations")
    
    st.markdown("""
    **Changes Made:**
    - Identified invalid expressions in calculation, required, relevant, constraint fields
    - Converted fields with invalid expressions to text type
    - Cleared problematic calculation formulas
    - Common issues fixed: pulldata(), duration(), broken XPath references
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Cleaning Calculations")
    st.dataframe(st.session_state.calculation_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.calculation_survey_df)
    st.download_button(
        label="Download Cleaned Calculations CSV for editing",
        data=csv_survey,
        file_name="survey_cleaned_calculations.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="calculation_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['calculation_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('calculations_cleaned', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'calculation_survey' in st.session_state.edited_dfs:
                st.session_state.calculation_survey_df = st.session_state.edited_dfs['calculation_survey']
            go_next()
            st.rerun()

def step_remove_invalid_defaults():
    st.header("Step 7: Remove Invalid Default Values")
    
    if st.session_state.calculation_survey_df is None:
        st.error("No calculation-cleaned survey data available. Please go back to step 6.")
        return
    
    # Display the before state
    st.subheader("Before Cleaning Default Values")
    with st.expander("View Survey Sheet Before Cleaning Defaults", expanded=False):
        st.dataframe(st.session_state.calculation_survey_df, use_container_width=True)
    
    # Apply default cleaning
    if 'defaults_cleaned' not in st.session_state:
        st.session_state.defaults_survey_df = clean_default_values(st.session_state.calculation_survey_df.copy())
        st.session_state.defaults_cleaned = True
    
    # Display the after state
    st.subheader("After Cleaning Default Values")
    
    st.markdown("""
    **Changes Made:**
    - Identified and removed default values containing expressions like `pulldata()` or `${...}`
    - Removed default values that reference deleted fields
    - This ensures all defaults will work properly in Kobo
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Cleaning Defaults")
    st.dataframe(st.session_state.defaults_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.defaults_survey_df)
    st.download_button(
        label="Download Cleaned Defaults CSV for editing",
        data=csv_survey,
        file_name="survey_cleaned_defaults.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="defaults_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['defaults_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('defaults_cleaned', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'defaults_survey' in st.session_state.edited_dfs:
                st.session_state.defaults_survey_df = st.session_state.edited_dfs['defaults_survey']
            go_next()
            st.rerun()

def step_normalize_field_names():
    st.header("Step 8: Normalize Field Names")
    
    if st.session_state.defaults_survey_df is None:
        st.error("No default-cleaned survey data available. Please go back to step 7.")
        return
    
    # Display the before state
    st.subheader("Before Normalizing Field Names")
    with st.expander("View Survey Sheet Before Name Normalization", expanded=False):
        st.dataframe(st.session_state.defaults_survey_df, use_container_width=True)
    
    # Apply name normalization
    if 'names_normalized' not in st.session_state:
        st.session_state.names_survey_df = ensure_unique_names(st.session_state.defaults_survey_df.copy())
        st.session_state.names_normalized = True
    
    # Display the after state
    st.subheader("After Normalizing Field Names")
    
    st.markdown("""
    **Changes Made:**
    - Converted all field names to lowercase
    - Replaced spaces with underscores
    - Removed invalid characters (keeping only a-z, 0-9, _)
    - Ensured all field names are unique (added suffixes if needed)
    """)
    
    # Find and highlight the changes
    if 'name' in st.session_state.defaults_survey_df.columns and 'name' in st.session_state.names_survey_df.columns:
        changed_rows = []
        for idx, row in st.session_state.names_survey_df.iterrows():
            if idx < len(st.session_state.defaults_survey_df):
                if row['name'] != st.session_state.defaults_survey_df.iloc[idx]['name']:
                    changed_rows.append({
                        'Row': idx + 1, 
                        'Original Name': st.session_state.defaults_survey_df.iloc[idx]['name'],
                        'Normalized Name': row['name']
                    })
        
        if changed_rows:
            st.subheader("Modified Field Names")
            st.dataframe(pd.DataFrame(changed_rows), use_container_width=True)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Name Normalization")
    st.dataframe(st.session_state.names_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.names_survey_df)
    st.download_button(
        label="Download Normalized Names CSV for editing",
        data=csv_survey,
        file_name="survey_normalized_names.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="names_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['names_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('names_normalized', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'names_survey' in st.session_state.edited_dfs:
                st.session_state.names_survey_df = st.session_state.edited_dfs['names_survey']
            go_next()
            st.rerun()

def step_validate_group_repeat_logic():
    st.header("Step 9: Validate Group & Repeat Logic")
    
    if st.session_state.names_survey_df is None:
        st.error("No name-normalized survey data available. Please go back to step 8.")
        return
    
    # Display the before state
    st.subheader("Before Validating Group/Repeat Logic")
    with st.expander("View Survey Sheet Before Group/Repeat Validation", expanded=False):
        st.dataframe(st.session_state.names_survey_df, use_container_width=True)
    
    # Apply group/repeat validation
    if 'groups_validated' not in st.session_state:
        st.session_state.groups_survey_df = validate_group_repeat_logic(st.session_state.names_survey_df.copy())
        st.session_state.groups_validated = True
    
    # Display the after state
    st.subheader("After Validating Group/Repeat Logic")
    
    if len(st.session_state.groups_survey_df) > len(st.session_state.names_survey_df):
        st.success("Missing group or repeat closing tags were added.")
    else:
        st.success("Group and repeat structure validated - no issues found.")
    
    st.markdown("""
    **Changes Made:**
    - Checked all begin/end group and begin/end repeat pairs
    - Added missing end tags if needed
    - Ensured proper nesting structure is maintained
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Survey Sheet After Group/Repeat Validation")
    st.dataframe(st.session_state.groups_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.groups_survey_df)
    st.download_button(
        label="Download Group/Repeat Validated CSV for editing",
        data=csv_survey,
        file_name="survey_validated_groups.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="groups_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['groups_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('groups_validated', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'groups_survey' in st.session_state.edited_dfs:
                st.session_state.groups_survey_df = st.session_state.edited_dfs['groups_survey']
            go_next()
            st.rerun()

def step_fix_cascading_selects():
    st.header("Step 10: Fix Cascading Selects")
    
    if st.session_state.groups_survey_df is None:
        st.error("No group-validated survey data available. Please go back to step 9.")
        return
    
    # Display the before state
    st.subheader("Before Fixing Cascading Selects")
    with st.expander("View Choices Sheet Before Fixing Cascading Selects", expanded=False):
        if st.session_state.normalized_choices_df is not None:
            st.dataframe(st.session_state.normalized_choices_df, use_container_width=True)
        else:
            st.info("No choices sheet available.")
    
    # Apply cascading select fixes
    if 'cascading_fixed' not in st.session_state:
        if st.session_state.normalized_choices_df is not None:
            st.session_state.cascading_choices_df = fix_cascading_selects(st.session_state.normalized_choices_df.copy())
        else:
            st.session_state.cascading_choices_df = create_standard_location_choices()
        st.session_state.cascading_fixed = True
    
    # Display the after state
    st.subheader("After Fixing Cascading Selects")
    
    st.markdown("""
    **Changes Made:**
    - Replaced any existing governorate, district, subdistrict entries
    - Inserted standardized location data with proper cascading structure
    - Ensured proper relationships between administrative levels
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display choices dataframe with download/upload options
    st.subheader("Choices Sheet After Fixing Cascading Selects")
    st.dataframe(st.session_state.cascading_choices_df, use_container_width=True)
    
    csv_choices = df_to_csv(st.session_state.cascading_choices_df)
    st.download_button(
        label="Download Fixed Choices CSV for editing",
        data=csv_choices,
        file_name="fixed_cascading_choices.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_choices = st.file_uploader("Upload edited Choices CSV", type=["csv"], key="cascading_choices_upload")
    if uploaded_choices is not None:
        edited_choices_df = csv_to_df(uploaded_choices)
        if edited_choices_df is not None:
            st.success("Choices CSV uploaded successfully!")
            st.session_state.edited_dfs['cascading_choices'] = edited_choices_df
            st.dataframe(edited_choices_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('cascading_fixed', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'cascading_choices' in st.session_state.edited_dfs:
                st.session_state.cascading_choices_df = st.session_state.edited_dfs['cascading_choices']
            go_next()
            st.rerun()

def step_check_settings_sheet():
    st.header("Step 11: Check Settings Sheet")
    
    if st.session_state.settings_df is None:
        st.error("No settings data available.")
        return
    
    # Display the before state
    st.subheader("Before Fixing Settings")
    with st.expander("View Settings Sheet Before Fixes", expanded=False):
        st.dataframe(st.session_state.settings_df, use_container_width=True)
    
    # Apply settings fixes
    if 'settings_fixed' not in st.session_state:
        st.session_state.fixed_settings_df = fix_settings_sheet(
            st.session_state.settings_df.copy(), 
            st.session_state.form_name
        )
        st.session_state.settings_fixed = True
    
    # Display the after state
    st.subheader("After Fixing Settings")
    
    st.markdown("""
    **Changes Made:**
    - Set default_language to English
    - Ensured form_id and form_title are filled
    - Used filename as fallback if needed
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display settings dataframe with download/upload options
    st.subheader("Settings Sheet After Fixes")
    st.dataframe(st.session_state.fixed_settings_df, use_container_width=True)
    
    csv_settings = df_to_csv(st.session_state.fixed_settings_df)
    st.download_button(
        label="Download Fixed Settings CSV for editing",
        data=csv_settings,
        file_name="fixed_settings.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_settings = st.file_uploader("Upload edited Settings CSV", type=["csv"], key="fixed_settings_upload")
    if uploaded_settings is not None:
        edited_settings_df = csv_to_df(uploaded_settings)
        if edited_settings_df is not None:
            st.success("Settings CSV uploaded successfully!")
            st.session_state.edited_dfs['fixed_settings'] = edited_settings_df
            st.dataframe(edited_settings_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('settings_fixed', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited version if available
            if 'fixed_settings' in st.session_state.edited_dfs:
                st.session_state.fixed_settings_df = st.session_state.edited_dfs['fixed_settings']
            go_next()
            st.rerun()

def step_remove_redundant_columns():
    st.header("Step 12: Remove Redundant Columns")
    
    if st.session_state.groups_survey_df is None or st.session_state.cascading_choices_df is None:
        st.error("Missing required data. Please complete previous steps.")
        return
    
    # Display the before state
    st.subheader("Before Removing Redundant Columns")
    
    with st.expander("View Survey Sheet Before Column Cleanup", expanded=False):
        st.dataframe(st.session_state.groups_survey_df, use_container_width=True)
    
    with st.expander("View Choices Sheet Before Column Cleanup", expanded=False):
        st.dataframe(st.session_state.cascading_choices_df, use_container_width=True)
    
    # Apply redundant column removal
    if 'columns_cleaned' not in st.session_state:
        st.session_state.final_survey_df = remove_redundant_columns(st.session_state.groups_survey_df.copy())
        st.session_state.final_choices_df = remove_redundant_columns(st.session_state.cascading_choices_df.copy())
        st.session_state.columns_cleaned = True
    
    # Display the after state
    st.subheader("After Removing Redundant Columns")
    
    st.markdown("""
    **Changes Made:**
    - Dropped empty columns
    - Removed unused advanced columns like style, readonly, publishable, etc.
    - Streamlined data for better performance and clarity
    """)
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Function to handle CSV uploads and convert back to dataframe
    def csv_to_df(uploaded_file):
        try:
            return pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return None
    
    # Display survey dataframe with download/upload options
    st.subheader("Final Survey Sheet")
    st.dataframe(st.session_state.final_survey_df, use_container_width=True)
    
    csv_survey = df_to_csv(st.session_state.final_survey_df)
    st.download_button(
        label="Download Final Survey CSV for editing",
        data=csv_survey,
        file_name="final_survey.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_survey = st.file_uploader("Upload edited Survey CSV", type=["csv"], key="final_survey_upload")
    if uploaded_survey is not None:
        edited_survey_df = csv_to_df(uploaded_survey)
        if edited_survey_df is not None:
            st.success("Survey CSV uploaded successfully!")
            st.session_state.edited_dfs['final_survey'] = edited_survey_df
            st.dataframe(edited_survey_df, use_container_width=True)
    
    # Display choices dataframe with download/upload options
    st.subheader("Final Choices Sheet")
    st.dataframe(st.session_state.final_choices_df, use_container_width=True)
    
    csv_choices = df_to_csv(st.session_state.final_choices_df)
    st.download_button(
        label="Download Final Choices CSV for editing",
        data=csv_choices,
        file_name="final_choices.csv",
        mime="text/csv",
    )
    
    st.write("If you want to make changes, download the CSV, edit it, and upload it back:")
    uploaded_choices = st.file_uploader("Upload edited Choices CSV", type=["csv"], key="final_choices_upload")
    if uploaded_choices is not None:
        edited_choices_df = csv_to_df(uploaded_choices)
        if edited_choices_df is not None:
            st.success("Choices CSV uploaded successfully!")
            st.session_state.edited_dfs['final_choices'] = edited_choices_df
            st.dataframe(edited_choices_df, use_container_width=True)
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            st.session_state.pop('columns_cleaned', None)
            go_back()
            st.rerun()
    with col2:
        if st.button("Next →"):
            # Update with edited versions if available
            if 'final_survey' in st.session_state.edited_dfs:
                st.session_state.final_survey_df = st.session_state.edited_dfs['final_survey']
            if 'final_choices' in st.session_state.edited_dfs:
                st.session_state.final_choices_df = st.session_state.edited_dfs['final_choices']
            go_next()
            st.rerun()

def step_export_file():
    st.header("Step 13: Export Kobo XLSForm")
    
    if (st.session_state.final_survey_df is None or 
        st.session_state.final_choices_df is None or 
        st.session_state.fixed_settings_df is None):
        st.error("Missing required data. Please complete previous steps.")
        return
    
    # Function to convert dataframe to CSV for download
    def df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')
    
    # Display each sheet separately instead of using tabs
    st.subheader("Survey Sheet Preview")
    st.dataframe(st.session_state.final_survey_df, use_container_width=True)
    csv_survey = df_to_csv(st.session_state.final_survey_df)
    st.download_button(
        label="Download Survey Sheet (CSV)",
        data=csv_survey,
        file_name="kobo_survey.csv",
        mime="text/csv",
    )
    
    st.subheader("Choices Sheet Preview")
    st.dataframe(st.session_state.final_choices_df, use_container_width=True)
    csv_choices = df_to_csv(st.session_state.final_choices_df)
    st.download_button(
        label="Download Choices Sheet (CSV)",
        data=csv_choices,
        file_name="kobo_choices.csv",
        mime="text/csv",
    )
    
    st.subheader("Settings Sheet Preview")
    st.dataframe(st.session_state.fixed_settings_df, use_container_width=True)
    csv_settings = df_to_csv(st.session_state.fixed_settings_df)
    st.download_button(
        label="Download Settings Sheet (CSV)",
        data=csv_settings,
        file_name="kobo_settings.csv",
        mime="text/csv",
    )
    
    st.markdown("---")
    st.subheader("Export Complete XLSForm")
    
    output_filename = st.text_input(
        "Output Filename", 
        value=f"{st.session_state.form_name}_kobo.xlsx"
    )
    
    if st.button("Generate XLSForm", type="primary"):
        try:
            output_file = create_excel_file(
                st.session_state.final_survey_df,
                st.session_state.final_choices_df,
                st.session_state.fixed_settings_df
            )
            
            st.success("Conversion completed successfully!")
            st.download_button(
                label="📥 Download Complete Kobo XLSForm",
                data=output_file,
                file_name=output_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Error generating Excel file: {str(e)}")
            st.info("You can still download individual sheets as CSV files above.")
    
    st.markdown("---")
    
    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Previous Step"):
            go_back()
            st.rerun()
    
    with col2:
        if st.button("Start Over"):
            # Reset all session state
            for key in list(st.session_state.keys()):
                if key != 'current_step':
                    st.session_state.pop(key, None)
            
            st.session_state.current_step = 0
            st.rerun()

# Main app flow based on current step
def main():
    # Display the current step
    if st.session_state.current_step == 0:
        step_upload_file()
    elif st.session_state.current_step == 1:
        step_load_core_sheets()
    elif st.session_state.current_step == 2:
        step_normalize_language_columns()
    elif st.session_state.current_step == 3:
        step_fix_field_types()
    elif st.session_state.current_step == 4:
        step_apply_label_fallbacks()
    elif st.session_state.current_step == 5:
        step_clean_calculation_fields()
    elif st.session_state.current_step == 6:
        step_remove_invalid_defaults()
    elif st.session_state.current_step == 7:
        step_normalize_field_names()
    elif st.session_state.current_step == 8:
        step_validate_group_repeat_logic()
    elif st.session_state.current_step == 9:
        step_fix_cascading_selects()
    elif st.session_state.current_step == 10:
        step_check_settings_sheet()
    elif st.session_state.current_step == 11:
        step_remove_redundant_columns()
    elif st.session_state.current_step == 12:
        step_export_file()

if __name__ == "__main__":
    main()