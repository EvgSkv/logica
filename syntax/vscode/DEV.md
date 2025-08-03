
# Development Instructions

## Installation

To install extention simply copy files into your VSCode extensions folder:
```
mkdir ~/.vscode/extensions/logica-syntax-highlighting-0.0.1
cp -r syntaxes package.json language-configuration.json ~/.vscode/extensions/logica-syntax-highlighting-0.0.1
```

You can also install this extension in Marketplace; or you can package the extension (as instructed below) and install the `vsix` file. 

## Quick Running

In VS Code open this folder (not from Logica folder, but as itself) and 

- click `Run and Debug` on your VS Code activity bar and then click the `Start Debugging` icon; OR
- press `F5` to open a new window with the extension loaded; OR
- hit `Ctrl+Shift+P` and run `>Debug: Start Debugging` in the Command Palette.


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


## Packaging and publishing

Install `vsce` on your machine:

```
npm install -g vsce
```

Your account needs to be added to our Azure DevOps organization `logicalang` and publisher `Logica` (due to some [bugs](https://stackoverflow.com/questions/56032912/vs-marketplace-add-member-displayes-invalid-domain-error) adding to publisher needs Microsoft support). Then generate a personal access token as described [here](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#publishing-extensions). 

Login your account with the access token:
```
vsce login <Your Account>
```

Generate a package and publish it (change `package.json` if needed):
```
vsce package
vsce publish
```


## References

https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide

https://macromates.com/manual/en/language_grammars
