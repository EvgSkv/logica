# logica-syntax-highlighting README

## Quick Running

In VS Code open this folder and 

- press `F5` to open a new window with the extension loaded; OR
- hit `Ctrl+Shift+P` and run `>Debug: Start Debugging` in the Command Palette; OR
- click `Run and Debug` on your VS Code activity bar and then click the `Start Debugging` icon.

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

```
mkdir ~/.vscode/extensions/logica-syntax-highlighting-0.0.1
cp -r syntaxes package.json language-configuration.json ~/.vscode/extensions/logica-syntax-highlighting-0.0.1
```

## References

https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide

https://macromates.com/manual/en/language_grammars