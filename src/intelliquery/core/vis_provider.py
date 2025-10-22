from __future__ import annotations
import abc
import json
import logging
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import importlib.resources

logger = logging.getLogger(__name__)


def _register_intelliquery_template():
    """
    Defines and registers a custom 'professional' Plotly template.
    This template includes a defined border and light grid for a more
    professional appearance.
    """
    import plotly.io as pio

    # Avoid re-registering the template if it already exists
    if "intelliquery_professional" in pio.templates:
        return

    pio.templates["intelliquery_professional"] = go.layout.Template(
        layout=go.Layout(
            font=dict(family="Arial, sans-serif", size=12, color="#333333"),
            title=dict(font=dict(size=20), x=0.5, xanchor="center"),
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(t=80, b=50, l=60, r=40),
            colorway=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"],
            # Apply a border and light grid to both axes
            xaxis=dict(
                showgrid=True,  # Enable light grid on x-axis
                gridcolor="#e9e9e9",
                zeroline=False,
                showline=True,  # Show axis line
                linecolor="#d9d9d9",
                mirror=True,  # Mirror axis line to create a full border
                tickfont=dict(color="#555555"),
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#e9e9e9",
                zeroline=False,
                showline=True,  # Show axis line
                linecolor="#d9d9d9",
                mirror=True,  # Mirror axis line to create a full border
                tickfont=dict(color="#555555"),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="#cccccc",
                borderwidth=1,
            ),
        )
    )
    # Set the new template as the default
    pio.templates.default = "intelliquery_professional"
    logger.info(
        "Registered and set 'intelliquery_professional' as default Plotly template."
    )


class VisualizationProvider(abc.ABC):
    """
    An abstract base class defining the contract for a visualization provider.
    """

    @abc.abstractmethod
    def create_chart(self, chart_type: str, dataframe: pd.DataFrame, **kwargs) -> Any:
        pass


class PlotlyProvider(VisualizationProvider):
    """
    A concrete implementation of the VisualizationProvider that uses the
    Plotly Express library to generate charts with a professional and
    data-aware style.
    """

    def __init__(self):
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        mapping_path = prompts_base_path / "vis_agent" / "vis_functions_mapping.json"
        try:
            with open(mapping_path) as f:
                self.vis_functions_mapping = json.load(f)
            # Register the professional template on initialization
            _register_intelliquery_template()
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load Plotly function mapping: {e}")
            self.vis_functions_mapping = {}

    def _apply_professional_styling(
        self, fig: go.Figure, chart_type: str, dataframe: pd.DataFrame, **kwargs
    ) -> go.Figure:
        """
        Applies dynamic, data-aware styling enhancements after a figure
        has been created.
        """
        try:
            # Smart Number Formatting for large numbers
            y_values = []
            if fig.data:
                for trace in fig.data:
                    if hasattr(trace, "y") and trace.y is not None:
                        y_values.extend(
                            [v for v in trace.y if isinstance(v, (int, float))]
                        )
            if y_values and max(y_values) > 1000:
                fig.update_yaxes(tickformat=",")

            # Hide legend if there's only one trace to de-clutter simple charts
            if len(fig.data) <= 1:
                fig.update_layout(showlegend=False)

            if chart_type in ["bar_chart", "histogram"]:
                # Add a subtle border to bars for better separation
                fig.update_traces(marker_line_width=1, marker_line_color="white")

                # Dynamic bar spacing based on number of categories
                if "x" in kwargs and kwargs["x"] in dataframe.columns:
                    num_categories = dataframe[kwargs["x"]].nunique()
                    if num_categories > 10:
                        # Reduce gap for many bars to avoid them being too thin
                        fig.update_layout(bargap=0.15)
                    else:
                        # Default gap for fewer bars
                        fig.update_layout(bargap=0.3)

            elif chart_type == "line_chart":
                mode = "lines+markers" if len(dataframe) <= 20 else "lines"
                fig.update_traces(line=dict(width=2.5), mode=mode)

            elif chart_type == "pie_chart":
                fig.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    hoverinfo="label+percent+value",
                    marker=dict(line=dict(color="white", width=2)),
                    pull=[0.05] * len(fig.data[0].values) if fig.data else [],
                )

        except Exception as e:
            logger.warning(
                f"Could not apply all professional styling enhancements: {e}"
            )
        return fig

    def create_chart(self, chart_type: str, dataframe: pd.DataFrame, **kwargs) -> Any:
        """
        Creates a Plotly chart, dynamically adjusting for user experience
        and applying professional styling.
        """
        logger.debug(f"Attempting to create Plotly chart of type '{chart_type}'.")

        function_path = self.vis_functions_mapping.get(chart_type)
        if not function_path:
            raise NotImplementedError(f"Chart type '{chart_type}' is not mapped.")

        function_name = function_path.split(".")[-1]
        if not hasattr(px, function_name):
            raise NotImplementedError(f"Plotly function '{function_name}' not found.")

        vis_func = getattr(px, function_name)
        execution_args = kwargs.copy()
        execution_args["data_frame"] = dataframe

        if chart_type == "bar_chart" and "x" in execution_args:
            x_column = execution_args["x"]
            # Ensure the column exists before checking its properties
            if x_column in dataframe.columns:
                num_categories = dataframe[x_column].nunique()
                # If more than 8 categories, switch to horizontal for readability
                if num_categories > 8 and "orientation" not in execution_args:
                    logger.info(
                        f"High cardinality ({num_categories} categories) detected. "
                        "Switching to horizontal bar chart for better readability."
                    )
                    execution_args["orientation"] = "h"
                    # Swap x and y for horizontal orientation
                    if "y" in execution_args:
                        y_column = execution_args.pop("y")
                        execution_args["x"], execution_args["y"] = (
                            execution_args.pop("x"),
                            y_column,
                        )

        # Generate the figure
        fig = vis_func(**execution_args)

        # Apply the final layer of styling
        fig = self._apply_professional_styling(fig, chart_type, dataframe, **kwargs)

        logger.info(f"Successfully generated and styled Plotly chart '{chart_type}'.")
        return fig
