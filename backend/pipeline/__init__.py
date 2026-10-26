class PipelineError(Exception):
    """A user-facing pipeline failure. The message is shown to the broker as-is."""
