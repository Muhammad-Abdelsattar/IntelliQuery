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
    Defines and registers our custom 'professional' Plotly template.
    This is the robust, framework-aligned way to handle the majority of styling.
    """
    import plotly.io as pio

    # Check if the template is already registered to avoid duplication
    if "intelliquery_professional" in pio.templates:
        return

    pio.templates["intelliquery_professional"] = go.layout.Template(
        layout=go.Layout(
            font=dict(family="Arial, sans-serif", size=12, color="#333"),
            title=dict(font=dict(size=20), x=0.5, xanchor="center"),
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(t=80, b=50, l=60, r=40),
            colorway=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"],
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                linecolor="#d9d9d9",
                tickfont=dict(color="#555"),
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#e9e9e9",
                zeroline=False,
                linecolor="#d9d9d9",
                tickfont=dict(color="#555"),
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
    # Set our new template as the default for all charts created in this session
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
    Plotly Express library to generate charts with a professional style.
    """

    def __init__(self):
        prompts_base_path = importlib.resources.files("intelliquery") / "prompts"
        mapping_path = prompts_base_path / "vis_agent" / "vis_functions_mapping.json"
        try:
            with open(mapping_path) as f:
                self.vis_functions_mapping = json.load(f)

            # Register the professional template once on initialization
            _register_intelliquery_template()

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load Plotly function mapping: {e}")
            self.vis_functions_mapping = {}

    def _apply_professional_styling(self, fig: go.Figure) -> go.Figure:
        """
        Applies dynamic, data-aware styling enhancements after a figure has
        been created. This adds the final layer of polish.
        """
        try:
            # Smart Number Formatting: Add comma separators for large numbers
            # This makes charts with large values (e.g., revenue) much more readable.
            y_values = []
            if fig.data:
                # Check all traces for 'y' or 'x' data to format
                for trace in fig.data:
                    if hasattr(trace, "y") and trace.y is not None:
                        y_values.extend(
                            [v for v in trace.y if isinstance(v, (int, float))]
                        )

            if y_values and max(y_values) > 1000:
                fig.update_yaxes(tickformat=",")

            # Conditional Legend Display: Hide legend if there's only one trace
            # This de-clutters simple charts automatically.
            if len(fig.data) <= 1:
                fig.update_layout(showlegend=False)

            # Trace-Specific Enhancements: Add subtle touches to common charts
            for trace in fig.data:
                # Add a subtle white border to bars for better separation
                if trace.type in ["bar", "histogram"]:
                    trace.update(marker=dict(line=dict(width=1, color="white")))
                # Slightly increase line width for better visibility in line charts
                elif trace.type == "scatter" and trace.mode and "lines" in trace.mode:
                    trace.update(line=dict(width=2.5))

        except Exception as e:
            logger.warning(
                f"Could not apply all professional styling enhancements: {e}"
            )

        return fig

    def create_chart(self, chart_type: str, dataframe: pd.DataFrame, **kwargs) -> Any:
        """
        Creates a Plotly chart using the professional template and applies
        final styling enhancements.
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


        fig = vis_func(**execution_args)

        fig = self._apply_professional_styling(fig)

        logger.info(f"Successfully generated and styled Plotly chart '{chart_type}'.")
        return fig
