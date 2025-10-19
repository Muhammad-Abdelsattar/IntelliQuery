import pandas as pd
import numpy as np
from typing import Dict, Any, List


def generate_dataframe_metadata(df: pd.DataFrame) -> str:
    """
    Analyzes a pandas DataFrame to generate structured metadata about its columns,
    inferring the type of each column (numerical, categorical, or temporal).

    Args:
        df: The pandas DataFrame to analyze.

    Returns:
        A dictionary containing the row count and a list of column metadata.
    """
    columns_metadata: List[Dict[str, str]] = []

    for col in df.columns:
        dtype = df[col].dtype
        col_metadata = {"name": str(col)}

        # Rule 1: Check for temporal types
        if pd.api.types.is_datetime64_any_dtype(dtype):
            col_metadata["type"] = "temporal"
        # Rule 2: Check for numerical types (int, float)
        elif pd.api.types.is_numeric_dtype(dtype):
            # Heuristic: If a numerical column has low cardinality, treat as categorical
            if df[col].nunique() < 25 and not pd.api.types.is_float_dtype(dtype):
                col_metadata["type"] = "categorical"
            else:
                col_metadata["type"] = "numerical"
        # Rule 3: Check for object/string types, likely categorical
        elif pd.api.types.is_object_dtype(dtype):
            col_metadata["type"] = "categorical"
        # Rule 4: Default fallback (less common types like boolean, timedelta)
        else:
            col_metadata["type"] = "categorical"  # Defaulting to categorical for safety

        columns_metadata.append(col_metadata)

    return f"Tha data has {len(df)} rows and {len(columns_metadata)} columns."
