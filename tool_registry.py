import tools

TOOLS = {
    "firefox": tools.firefox,
    "vscode": tools.vscode,
    "open_url": tools.open_url,
    "run_python": tools.run_python,
    "list_files": tools.list_files,
    "read_file": tools.read_file,
    "write_file": tools.write_file,
    "append_to_file": tools.append_to_file,
    "create_markdown_doc": tools.create_markdown_doc,
    "add_calendar_event": tools.add_calendar_event,
    "list_calendar_events": tools.list_calendar_events,
    "clear_calendar": tools.clear_calendar,
    "system_terminal_command": tools.system_terminal_command,
    "google_docs": tools.google_docs_tool,
    "googledocs": tools.google_docs_tool,  # <-- Se ele esquecer o underline, aponta para a mesma função!
    "upload_to_drive": tools.upload_to_drive,
    "enviar_pasta_para_drive": tools.enviar_pasta_para_drive
}