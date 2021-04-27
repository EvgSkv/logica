# logica-syntax-highlighting README

## Quick Running

In VS Code open this folder and press `F5` to open a new window with the extension loaded.

## Development

Install `js-yaml` as a development only dependency in the extension:

```
npm install js-yaml --save-dev
```

Edit `src/logica.tmLanguage.yaml`, which is written in TextMate grammar.

Convert `yaml` to `json` with the command-line tool:

```
npx js-yaml src/logica.tmLanguage.yaml > syntaxes/logica.tmLanguage.json
```


## Installation

To start using your extension with Visual Studio Code copy it into the `<user home>/.vscode/extensions` folder and restart Code.

## References

https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide

https://macromates.com/manual/en/language_grammars