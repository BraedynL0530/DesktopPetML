from flask import Flask, jsonify, request

from core.local_agent_service import LocalAgentService

app = Flask(__name__)
service = LocalAgentService()


@app.post('/task')
def task():
    body = request.get_json(silent=True) or {}
    task_type = (body.get('task_type') or '').strip().lower()
    content = body.get('content', '')

    if task_type == 'summary':
        items = content if isinstance(content, list) else [str(content)]
        result = service.daily_summary(items)
    elif task_type == 'outline':
        result = service.create_outline(str(content))
    elif task_type == 'graph':
        result = service.create_graph(str(content))
    else:
        return jsonify({'ok': False, 'error': 'Unknown task_type'}), 400

    return jsonify({'ok': True, 'result': result})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5061, debug=False)
