# Document Intelligence
PyQt6 app for evaluating Azure DI vs custom/trained models for form reading.

The app supports multiple form types, aka "Projects". These have differing form layouts and different indexing requirements.

Files are of type PDF or TIFF, are often multipage, and contain scanned images.

# Stage 1: Rented GPU with trained VLM

## Layout

### Left panel
Table containing list of filenames followed by *index_fields*- values returned from the endpoint.

### Right panel
Image viewer for the current

## Menus

*File -> Load Configuration*: Subdirectories of env variable FORM_CONFIG_DIRECTORY name projects. This menu item loads the basic config file for the current project (name: env.BASE_CONFIG_FILENAME), and the remaining configuration for the project is read from there.

*File -> Load Images*: Opens a file picker allowing the user to select multiple files for processing. The file picker defaults to the directory specified in the config file, *default_image_directory*.

On re-opening the app, the previous configuration and file list are restored from the user's APPDATA.

*File -> Upload*: Submits the files to the endpoint, and updates *index_fields* with the responses.


