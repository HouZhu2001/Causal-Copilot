import json


class Programming(object):
    # Kun Zhou Implemented
    def __init__(self, args):
        self.args = args
        f = open(f"algorithm/context/algo2code.json", "r")
        self.algo2example_code = {}
        for line in f:
            lines = json.loads(line.strip())
            self.algo2example_code[lines['algo']] = lines['code']

    def extract(self, output, start_str, end_str):
        if start_str in output and end_str in output:
            try:
                algo = output.split(start_str)[1].split(end_str)[0]
            except:
                algo = ''
            if '```python' in algo:
                algo = algo.split('```python')[1].split('```')[0].strip()
            return algo
        else:
            return ''

    def code_synthesis(self, algorithm, algorithm_setup):
        '''

        :param data: Given Tabular Data in Pandas DataFrame format
        :param algorithm_setup: A dict containing the selected algorithm and its hyperparameter settings
        :return: executable programs based on Causal-Learn Toolkit
        '''
        from openai import OpenAI
        client = OpenAI(organization=self.args.organization, project=self.args.project, api_key=self.args.apikey)
        algo_example = self.algo2example_code[algorithm]
        prompt = (("Please rewrite the following example code with default arguments, to use %s algorithm for causal discovery:\n\n"
                  "%s\n\nHere, we get the suggestions about its arguments as below:\n\n"
                  "%s\n\nBased on the suggestion, please only modify the values of related arguments in the example code as few as possible, and do not add any new arguments!\n"
                   "Finally generate the rewrited python code using the following template <Code>executable code</Code>")
                  % (algorithm, algo_example, algorithm_setup))
        code = ''
        while code == '':
            print("The prompt for code generation is: -------------------------------------------------------------------------")
            print(prompt)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            output = response.choices[0].message.content
            print("The received output for code is: -------------------------------------------------------------------------")
            print(output)
            code = self.extract(output, "<Code>", "</Code>")
            print(code)
        return code

    def execute(self, pd_data, program):
        '''
        :param program: Causal-Learn Toolkit program
        :return: A numpy: adj binary matrix (variable relation), Matrix[i,j] denotes j->i
        '''
        from causallearn.search.ConstraintBased.PC import pc
        from causallearn.search.ConstraintBased.FCI import fci
        from causallearn.search.ConstraintBased.CDNOD import cdnod
        from causallearn.search.ScoreBased.GES import ges
        from causallearn.search.FCMBased import lingam
        data = pd_data.to_numpy()

        global graph
        graph = None
        local_scope = {'data': data, 'pc': pc, 'fci': fci, 'cdnod': cdnod, 'ges': ges, 'lingam': lingam, 'graph': graph}
        try:
            exec(program, globals(), local_scope)
            graph = local_scope['graph']
            print(graph.G)
            results = graph.G.graph
        except:
            print("Execution failed")
            results = None
        return results

    def forward(self, data, algorithm, algorithm_setup):
        '''

        :param data: Given Tabular Data in Pandas DataFrame format
        :param algorithm: Selected algorithm
        :param algorithm_setup: A dict containing the selected algorithm and its hyperparameter settings
        :return: executable programs based on Causal-Learn Toolkit
        '''
        results = None
        while results is None:
            program = self.code_synthesis(algorithm, algorithm_setup)
            print("The final code for execution is: -------------------------------------------------------------------------")
            print(program)
            results = self.execute(data, program)
        return program, results