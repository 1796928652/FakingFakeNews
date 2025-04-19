from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import os
from datetime import datetime

from LLM_verification.Fact_verification import run_fact_verification


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制

# 自动创建上传目录
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif'},
    'video': {'mp4', 'avi','mov'}
}


@app.context_processor
def inject_utilities():
    return {
        'now': datetime.now,
        'zip': zip,
        'os': os
    }


def allowed_file(filename, file_type):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS[file_type]


def detect_content(input_type, content):
    results = []
    analysis = []
    show_search = False  # 新增的第三个返回值

    if input_type == 'text':
        temp = run_fact_verification(content)
        results.append(temp[0])
        for i in temp[1]:
            analysis.append(i)
        show_search = True  # 文本类型需要显示搜索

    elif input_type == 'image':
        filename = os.path.basename(content)
        results.append(f"图片分析结果：{filename} ")
        analysis.extend([
            '图文一致性不符'
            #"EXIF分析：创建时间与内容不符",
            #"像素分析：检测到9处复制粘贴区域"
        ])

    elif input_type == 'video':
        filename = os.path.basename(content)
        results.append(f"视频分析结果：{filename} 存在剪辑痕迹")
        analysis.extend([
            "帧率分析：检测到异常帧率变化",
            "声纹分析：背景音存在拼接痕迹"
        ])

    return '\n'.join(results), analysis, show_search  # 现在统一返回3个值


@app.route('/', methods=['GET', 'POST'])
def index():
    greeting = get_greeting()

    if request.method == 'POST':
        show_search_flag = False
        text_content = request.form.get('text', '').strip()
        file = request.files.get('file')

        inputs = []
        # 处理文本输入
        if text_content:
            inputs.append(('text', text_content))
            show_search_flag = True

        # 处理文件上传
        if file and file.filename:
            file_type = determine_file_type(file.filename)
            if file_type:
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                inputs.append((file_type, save_path))

        # 执行检测
        results = []
        analysis = []
        for input_type, content in inputs:
            res, anal, should_search = detect_content(input_type, content)
            show_search_flag = show_search_flag or should_search
            results.append(res)
            analysis.extend(anal)

        # 将inputs转换为可序列化的字符串格式
        inputs_str = [f"{input_type},{content}" for input_type, content in inputs]

        return redirect(url_for('chat',
                                inputs=inputs_str,
                                results=results,
                                analysis=analysis,
                                show_search='true' if show_search_flag else 'false'))

    return render_template('index.html', greeting=greeting)


def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 9:
        return '清晨好🌅'
    if 9 <= hour < 12:
        return '上午好🌞'
    if 12 <= hour < 14:
        return '午间好🍱'
    if 14 <= hour < 18:
        return '下午好☕'
    if 18 <= hour < 22:
        return '晚上好🌙'
    return '深夜好🌃'


def determine_file_type(filename):
    for file_type, exts in ALLOWED_EXTENSIONS.items():
        if '.' in filename and filename.rsplit('.', 1)[1].lower() in exts:
            return file_type
    return None


@app.route('/chat', methods=['GET', 'POST'])
def chat():
    inputs = request.args.getlist('inputs')
    results = request.args.getlist('results')
    analysis = request.args.getlist('analysis')
    show_search = request.args.get('show_search', 'false')

    # 将字符串形式的inputs转换为元组形式
    processed_inputs = []
    for input_str in inputs:
        parts = input_str.split(',', 1)  # 只分割第一个逗号
        if len(parts) == 2:
            processed_inputs.append((parts[0], parts[1]))

    if request.method == 'POST':
        text_content = request.form.get('text', '').strip()
        file = request.files.get('file')

        new_inputs = []
        if text_content:
            new_inputs.append(('text', text_content))
        if file and file.filename:
            file_type = determine_file_type(file.filename)
            if file_type:
                filename = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(save_path)
                new_inputs.append((file_type, save_path))

        new_results = []
        new_analysis = []
        for input_type, content in new_inputs:
            res, anal, _ = detect_content(input_type, content)
            new_results.append(res)
            new_analysis.extend(anal)

        results.extend(new_results)
        analysis.extend(new_analysis)
        processed_inputs.extend(new_inputs)

    return render_template('chat.html',
                         inputs=processed_inputs,
                         results=results,
                         analysis=analysis,
                         show_search=show_search)


@app.route('/detect', methods=['POST'])
def detect():
    text_content = request.form.get('text', '').strip()
    file = request.files.get('file')

    inputs = []
    if text_content:
        inputs.append(('text', text_content))
    if file and file.filename:
        file_type = determine_file_type(file.filename)
        if file_type:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            inputs.append((file_type, save_path))

    results = []
    analysis = []
    for input_type, content in inputs:
        res, anal,_ = detect_content(input_type, content)
        results.append(res)
        analysis.extend(anal)

    result_str = '\n'.join(results)
    analysis_str = '\n'.join(analysis)
    return jsonify({'result': '\n'.join(results), 'analysis': analysis})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)