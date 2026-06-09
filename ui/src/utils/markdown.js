import MarkdownIt from "markdown-it";
import Prism from "prismjs";

import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-markup";
import "prismjs/components/prism-css";
import "prismjs/components/prism-rust";
import "prismjs/components/prism-go";
import "prismjs/components/prism-java";
import "prismjs/components/prism-c";
import "prismjs/components/prism-cpp";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-toml";
import "prismjs/components/prism-docker";

const md = new MarkdownIt({
  linkify: true,
  typographer: true,
  highlight(str, lang) {
    const grammar = lang && Prism.languages[lang];
    const code = grammar
      ? Prism.highlight(str, grammar, lang)
      : md.utils.escapeHtml(str);
    return `<pre class="language-${lang || "none"}"><code class="language-${lang || "none"}">${code}</code></pre>`;
  },
});

export const renderMarkdown = (text) => md.render(text ?? "");
