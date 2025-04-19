'''
大语言模型阶梯式可解释性验证(deepseek)
'''
import requests
import ast
import re
from typing import Optional, Dict


DEEPSEEK_API_KEY = "sk-58652c7be96e49f9becf32830b488927"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"#"https://api.deepseek.com"


PROGRAM_PROMPT = """请生成符合Python语法的验证程序，不需要注释 要求：
1. 使用函数：question() 获取信息，verify() 核实一个简单声明， predict() 预测准确的标签
2. 变量名：ans1/fact1 格式
3. 直接使用Python表达式验证
4. 最终返回布尔值label (不允许使用not)

示例：
声明：北京和上海都是直辖市
程序：
ans1 = question("北京是直辖市吗")
fact1 = (ans1 == True)
ans2 = question("上海是直辖市吗")
fact2 = (ans2 == False)
label = fact1 and fact2

当前声明：{claim}
生成程序："""


class FactVerifier:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        })
        self.exp = []

    #@lru_cache(maxsize=100)
    def question(self, query: str) -> str:
        """带缓存的知识查询"""
        try:
            response = self.session.post(
                DEEPSEEK_ENDPOINT,
                json={
                    "model": "deepseek-chat",
                    "messages": [{
                        "role": "user",
                        "content": f"先回答True or False 再用一句话解释：{query}"
                    }],
                    "temperature": 0.3,
                    "max_tokens": 50
                },
                timeout=10
            )
            if response.status_code == 200:
                answer = response.json()['choices'][0]['message']['content']
                #print(answer)
                self.exp.append(answer[6:])
                return self._clean_answer(answer)
        except Exception as e:
            print(f"查询失败：{str(e)}")
        return "未知"

    def _clean_answer(self, text: str) -> str:
        """清洗回答结果"""
        text = re.sub(r"[。，、；：“”‘’]", "", text)
        #print("raw_text:", text)
        match = re.search(r"^(是|否)", text)

        return match.group(0) if match else "未知"


    def generate_program(self, claim: str) -> Optional[str]:
        """生成验证程序"""
        try:
            response = self.session.post(
                DEEPSEEK_ENDPOINT,
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": PROGRAM_PROMPT.format(claim=claim)}],
                    "temperature": 0.3,
                    "max_tokens": 600
                },
                timeout=20
            )
            #print("response.status_code", response.status_code)
            if response.status_code == 200:
                return self._process_code(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            print(f"程序生成失败：{str(e)}")
        return None

    def _process_code(self, raw_code: str) -> Optional[str]:
        """代码后处理"""
        # 替换中文残留
        replacements = {
            "问题": "question",
            "答案": "ans",
            "事实": "fact",
            "标签": "label",
            "且": "and",
            "或": "or",
            "等于": "=="
        }
        processed_code = raw_code
        for cn, en in replacements.items():
            processed_code = processed_code.replace(cn, en)
        #   确定 确实时反引号的问题！
        processed_code = processed_code.replace("```", "")
        #print(processed_code)

        # 语法验证
        try:
            ast.parse(processed_code)
            return processed_code
        except SyntaxError as e:
            print(f"语法错误：{str(e)}")
            return None

    def verify(self, claim: str) -> Dict:
        """执行完整验证流程"""
        program = self.generate_program(claim)

        if not program:
            return {"status": "error", "message": "程序生成失败"}

        try:
            env = {"question": self.question, "__builtins__": None}
            exec(program, env)

            result = env.get('label', False)

            # 构建解释
            explanation = {
                "steps": [],
                "variables": {k: v for k, v in env.items() if k.startswith(('ans', 'fact'))}
            }


            # 解析程序步骤
            for line in program.split('\n'):
                if line.strip().startswith(('ans', 'fact', 'label')):
                    explanation["steps"].append(line.strip())
            #print("explanation:", explanation)

            return {
                "status": "success",
                "result": result,
                "explanation": explanation,
                "raw_program": program
            }
        except Exception as e:
            return {"status": "error", "message": f"执行错误：{str(e)}"}


def run_fact_verification(claim):
    verifier = FactVerifier()

    print(f"验证声明：{claim}")
    report = verifier.verify(claim)

    if report["status"] == "success":
        print("验证步骤：")
        for step in report["explanation"]["steps"]:
            print(f"  - {step}")
        print(f"验证结果：{'成立' if report['result'] else '声明存疑'}")
    else:
        print(f"验证失败：{report['message']}")
    for explanation in verifier.exp:
        print("理由：", explanation)

    print("=" * 50)
    return '可信' if report['result'] else '存疑', verifier.exp



if __name__ == "__main__":


    claim = "喝可乐会杀精"
    run_fact_verification(claim)
