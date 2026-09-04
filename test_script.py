from charles_analizer.parser import CharlesSessionParser
from charles_analizer.analyzer import CharlesAnalyzer
from server import CharlesWebHandler
import json, re

parser = CharlesSessionParser('example_0.chls')
reqs = parser.parse()
analyzer = CharlesAnalyzer(reqs)
session_data = {
    'summary': analyzer.summary(),
    'requests': [r.to_dict(include_bodies=True) for r in reqs]
}

handler = CharlesWebHandler.__new__(CharlesWebHandler)
html = handler.render_web_app_html()

scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
full_js = '\n'.join(scripts)

with open('test_modal_exec.js', 'w') as f:
    f.write('const jsdom = require("jsdom");\n')
    f.write('const { JSDOM } = jsdom;\n')
    f.write('const dom = new JSDOM(' + json.dumps(html) + ');\n')
    f.write('global.window = dom.window;\n')
    f.write('global.document = dom.window.document;\n')
    f.write('global.navigator = dom.window.navigator;\n')
    f.write('global.URLSearchParams = dom.window.URLSearchParams;\n')
    f.write(full_js + '\n')
    f.write('currentSessionData = ' + json.dumps(session_data) + ';\n')
    f.write('activeRequestsList = [...currentSessionData.requests];\n')
    f.write('''
console.log("Testing openInspector for all " + activeRequestsList.length + " requests...");
let errorCount = 0;
for (const req of activeRequestsList) {
    try {
        openInspector(req.id);
    } catch (e) {
        console.error("ERROR opening req #" + req.id + ": " + e.message + "\\n" + e.stack);
        errorCount++;
    }
}
console.log("Finished testing openInspector. Errors: " + errorCount);
''')

