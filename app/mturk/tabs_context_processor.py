def tabs(request):
    path = request.path_info
    top_tab = 'start'

    if path.startswith('/requester_details') or path.startswith('/hit/'):
        top_tab = 'top_requesters'
    elif path.startswith('/docs/'):
        top_tab = 'docs'
    elif path != "/":
        top_tab = path.replace('/', '')

    return {
        'top_tab': top_tab
    }
