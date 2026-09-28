import os, io

base = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(os.path.dirname(base), 'system.py')

read = lambda p: io.open(p, 'r', encoding='utf-8').read()

skeleton = read(os.path.join(base, '_skeleton.py'))
index_html = read(os.path.join(base, 'templates', 'index.html'))
styles_css = read(os.path.join(base, 'static', 'styles.css'))
enroll_html = read(os.path.join(base, 'templates', 'enroll.html'))

index_html = index_html.replace(
    '<link rel="stylesheet" href="/static/styles.css">',
    '<style>\n' + styles_css + '\n</style>'
)

assert '__INDEX_HTML__' in skeleton and '__ENROLL_HTML__' in skeleton

result = skeleton.replace('__INDEX_HTML__', index_html).replace('__ENROLL_HTML__', enroll_html)

io.open(out, 'w', encoding='utf-8', newline='\n').write(result)
print('written:', out, len(result), 'bytes')