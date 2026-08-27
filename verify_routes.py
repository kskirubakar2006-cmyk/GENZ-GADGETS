from app import app

client = app.test_client()
for path in ['/', '/login', '/dashboard', '/logout']:
    response = client.get(path, follow_redirects=False)
    print('PATH', path)
    print('STATUS', response.status_code)
    print('LOCATION', response.headers.get('Location'))
    if response.status_code == 200:
        html = response.get_data(as_text=True)
        title = ''
        start = html.find('<title>')
        end = html.find('</title>')
        if start != -1 and end != -1:
            title = html[start + 7:end].strip()
        print('TITLE', title)
    print('---')
