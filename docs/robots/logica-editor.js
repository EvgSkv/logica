/**
 * Logica Editor - Pretty syntax highlighting for Logica code
 * 
 * Usage:
 *   import { PrettyEditor } from './logica-editor.js';
 *   const editor = PrettyEditor("my_textarea_id");
 * 
 * Requires CodeMirror 5 to be loaded first:
 *   <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5.65.16/lib/codemirror.css">
 *   <script src="https://cdn.jsdelivr.net/npm/codemirror@5.65.16/lib/codemirror.js"></script>
 */

// Define Logica mode for CodeMirror
CodeMirror.defineMode("logica", function() {
  return {
    startState: function() {
      return {
        inBlockComment: false,
        inTripleString: false
      };
    },

    token: function(stream, state) {
      // Inside block comment
      if (state.inBlockComment) {
        if (stream.match(/.*?\*\//)) {
          state.inBlockComment = false;
        } else {
          stream.skipToEnd();
        }
        return "comment";
      }

      // Inside triple-quoted string
      if (state.inTripleString) {
        if (stream.match(/.*?"""/)) {
          state.inTripleString = false;
        } else {
          stream.skipToEnd();
        }
        return "string";
      }

      // Skip whitespace
      if (stream.eatSpace()) return null;

      // Block comment start
      if (stream.match(/\/\*/)) {
        state.inBlockComment = true;
        return "comment";
      }

      // Line comment
      if (stream.match(/#.*/)) {
        return "comment";
      }

      // Triple-quoted string start
      if (stream.match('"""')) {
        state.inTripleString = true;
        return "string";
      }

      // Regular string
      if (stream.match(/"[^"]*"/)) {
        return "string";
      }

      // Keywords
      if (stream.match(/\b(if|then|else|distinct|in|is|import|as|not)\b/)) {
        return "keyword";
      }

      // Constants
      if (stream.match(/\b(null|true|false)\b/)) {
        return "atom";
      }

      // Operators (multi-char first)
      if (stream.match(/:-|:=|\+=|==|!~|->|>=|<=|!=|&&|\|\|/)) {
        return "operator";
      }
      if (stream.match(/[*+\/%<>\-=]/)) {
        return "operator";
      }

      // Annotations (@Ground, @OrderBy, etc.)
      if (stream.match(/@[A-Z]\w*/)) {
        return "meta";
      }

      // Field access (.field_name)
      if (stream.match(/\.[a-z_]\w*/)) {
        return "property";
      }

      // Named arguments (name:) - lookahead for colon
      if (stream.match(/[a-z_]\w*(?=:)/)) {
        return "def";
      }

      // Numbers (float first, then int)
      if (stream.match(/\d+\.\d+/) || stream.match(/\d+/)) {
        return "number";
      }

      // Predicates and aggregations (capitalized)
      if (stream.match(/\b[A-Z]\w*/)) {
        return "variable-2";
      }

      // Variables (lowercase)
      if (stream.match(/\b[a-z_]\w*/)) {
        return "variable";
      }

      // Brackets and punctuation
      if (stream.match(/[{}()\[\];,]/)) {
        return "bracket";
      }

      // Consume any other character
      stream.next();
      return null;
    }
  };
});

// Mariana theme styles
const MARIANA_STYLES = `
/* Base theme */
.cm-s-logica-mariana.CodeMirror {
  background: hsl(210, 15%, 22%);
  color: hsl(219, 28%, 88%);
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.9rem;
  line-height: 1.4;
  border: 1px solid #3a3a3a;
  border-radius: 8px;
  padding: 0.5rem 0;
  height: 600px;
}

/* Per-editor height overrides */
textarea#robotProgram + .CodeMirror.cm-s-logica-mariana {
  height: 600px;
}
textarea#debugProgram + .CodeMirror.cm-s-logica-mariana {
  height: 100%;
}

.cm-s-logica-mariana .CodeMirror-gutters {
  background: hsl(210, 15%, 20%);
  border-right: 1px solid hsl(210, 13%, 30%);
  padding-left: 2px;
}
.cm-s-logica-mariana .CodeMirror-linenumber {
  color: hsl(210, 13%, 45%);
  padding-right: 10px;
  padding-left: 0px;
}

.cm-s-logica-mariana .CodeMirror-lines {
  padding-left: 4px;
}

.cm-s-logica-mariana .CodeMirror-cursor {
  border-left: 2px solid hsl(32, 93%, 66%);
}
.cm-s-logica-mariana .CodeMirror-selected {
  background: hsla(210, 13%, 40%, 0.7);
}
.cm-s-logica-mariana .CodeMirror-activeline-background {
  background: hsla(210, 13%, 40%, 0.3);
}
.cm-s-logica-mariana .cm-comment {
  color: hsl(221, 12%, 69%);
}
.cm-s-logica-mariana .cm-string {
  color: hsl(114, 31%, 68%);
}
.cm-s-logica-mariana .cm-number {
  color: hsl(32, 93%, 66%);
}
.cm-s-logica-mariana .cm-keyword {
  color: hsl(300, 30%, 68%);
}
.cm-s-logica-mariana .cm-atom {
  color: hsl(357, 79%, 65%);
  font-style: italic;
}
.cm-s-logica-mariana .cm-operator {
  color: hsl(219, 28%, 88%);
}
.cm-s-logica-mariana .cm-meta {
  color: hsl(210, 50%, 60%);
}
.cm-s-logica-mariana .cm-property {
  color: hsl(219, 28%, 88%);
  font-style: italic;
}
.cm-s-logica-mariana .cm-def {
  color: hsl(32, 93%, 66%);
}
.cm-s-logica-mariana .cm-variable {
  color: hsl(219, 28%, 88%);
}
.cm-s-logica-mariana .cm-variable-2 {
  color: hsl(180, 36%, 54%);
}
.cm-s-logica-mariana .cm-bracket {
  color: hsl(0, 0%, 100%);
}
`;

// Inject styles once
let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  const style = document.createElement('style');
  style.textContent = MARIANA_STYLES;
  document.head.appendChild(style);
  stylesInjected = true;
}

/**
 * Create a pretty Logica editor from a textarea
 * @param {string} elementId - ID of the textarea element
 * @param {object} options - Additional CodeMirror options (optional)
 * @returns {CodeMirror.Editor} - The CodeMirror editor instance
 */
function PrettyEditor(elementId, options = {}) {
  injectStyles();
  
  const textarea = document.getElementById(elementId);
  if (!textarea) {
    throw new Error(`Element with id "${elementId}" not found`);
  }

  const defaultOptions = {
    mode: 'logica',
    theme: 'logica-mariana',
    lineNumbers: true,
    lineWrapping: true
  };

  const editor = CodeMirror.fromTextArea(textarea, { ...defaultOptions, ...options });
  
  // Proxy the textarea's .value property to sync with CodeMirror
  Object.defineProperty(textarea, 'value', {
    get() {
      return editor.getValue();
    },
    set(v) {
      editor.setValue(v);
    }
  });

  return editor;
}

// Export for ES modules
export { PrettyEditor };

// Also attach to window for non-module usage
if (typeof window !== 'undefined') {
  window.PrettyEditor = PrettyEditor;
}