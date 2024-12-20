import gradio as gr
import pandas as pd
import io
import os
import shutil
from datetime import datetime
import sys
from queue import Queue

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Gradio.demo_config import get_demo_config
from global_setting.Initialize_state import global_state_initialization
from preprocess.stat_info_functions import stat_info_collection, convert_stat_info_to_text
from preprocess.dataset import knowledge_info
from preprocess.eda_generation import EDA
from algorithm.filter import Filter
from algorithm.program import Programming
from algorithm.rerank import Reranker
from postprocess.judge import Judge
from postprocess.visualization import Visualization
from postprocess.report_generation import Report_generation
from user.discuss import Discussion

# Global variables
UPLOAD_FOLDER = "./demo_data"
chat_history = []
target_path = None
output_dir = None
REQUIRED_INFO = {
    'data_uploaded': False,
    'initial_query': False,
    "processing_discussion": False,
}
MAX_CONCURRENT_REQUESTS = 5
MAX_QUEUE_SIZE = 10

# Demo dataset configs
DEMO_DATASETS = {
    "Abalone": {
        "name": "🐚 Real Dataset:Abalone",
        "path": "dataset/Abalone/Abalone.csv",
        "query": "YES. Find causal relationships between physical measurements and age of abalone. The dataset contains numerical measurements of physical characteristics.",
    },
    "Sachs": {
        "name": "🧬 Real Dataset: Sachs",
        "path": "dataset/sachs/sachs.csv", 
        "query": "YES. Discover causal relationships between protein signaling molecules. The data contains flow cytometry measurements of proteins and phospholipids."
    },
    "CCS Data": {
        "name": "📊 Real Dataset: CCS Data",
        "path": "dataset/CCS_Data/CCS_Data.csv",
        "query": "YES. Analyze causal relationships between variables in the CCS dataset. The data contains multiple continuous variables."
    },
    "Ozone": {
        "name": "🌫️ Real Dataset: Ozone", 
        "path": "dataset/Ozone/Ozone.csv",
        "query": "YES. This is a Time-Series dataset, investigate causal factors affecting ozone levels. The data contains atmospheric and weather measurements over time."
    },
    "Linear_Gaussian": {
        "name": "🟦 Simulated Data: Linear Gaussian",
        "path": "dataset/Linear_Gaussian/Linear_Gaussian_data.csv",
        "query": "NO. The data follows linear relationships with Gaussian noise. Please discover the causal structure."
    },
    "Linear_Nongaussian": {
        "name": "🟩 Simulated Data: Linear Non-Gaussian",
        "path": "dataset/Linear_Nongaussian/Linear_Nongaussian_data.csv", 
        "query": "NO. The data follows linear relationships with non-Gaussian noise. Please discover the causal structure."
    }
}


def upload_file(file):
    # TODO: add more complicated file unique ID handling
    global target_path, output_dir

    date_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(file.name).replace('.csv', '')), exist_ok=True)

    target_path = os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(file.name).replace('.csv', ''),
                               os.path.basename(file.name))
    output_dir = os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(file.name).replace('.csv', ''))
    shutil.copy(file.name, target_path)
    return target_path


def handle_file_upload(file, chatbot, file_upload_btn, download_btn):
    chatbot = chatbot.copy()
    try:
        global REQUIRED_INFO
        if file.name.endswith('.csv'):
            df = pd.read_csv(file.name)
            upload_file(file)
            REQUIRED_INFO['data_uploaded'] = True
            bot_message = (f"✅ Successfully loaded CSV file with {len(df)} rows and {len(df.columns)} columns! \n"
                           "🤔 Please follow the guidances above for your initial query. \n"
                           "✨ It would be super helpful if you can include more relevant information, e.g., background/context/prior/statistical information!")
        else:
            bot_message = "❌ Please upload a CSV file."
        chatbot.append((None, bot_message))
        return chatbot, file_upload_btn, download_btn

    except Exception as e:
        error_message = f"❌ Error loading file: {str(e)}"
        chatbot.append((None, error_message))
        return chatbot, file_upload_btn, download_btn


def process_initial_query(message, chat_history, args):
    global REQUIRED_INFO
    # TODO: check if the initial query is valid or satisfies the requirements
    print('initial query:', message)
    if 'YES' in message:
        args.data_mode = 'real'
        REQUIRED_INFO['initial_query'] = True
        chat_history.append((message, None))
    elif 'NO' in message:
        args.data_mode = 'simulated'
        REQUIRED_INFO['initial_query'] = True
        chat_history.append((message, None))
    else:
        print('not feature indicator')
        chat_history.append((message,
                                """Please enter your initial query first before proceeding. 
                             Please indicate if your dataset has meaningful feature names using 'YES' or 'NO', 
                             and you can also provide some information about the background/context/prior/statistical information about the dataset,
                             which would help us generate appropriate report for you.
                             """))
        #yield chat_history, download_btn
    return args, chat_history, download_btn


def process_message(message, chat_history, download_btn):
    global target_path, REQUIRED_INFO
    REQUIRED_INFO['processing'] = True
    # Add user message
    # chat_history.append((message, None))
    # yield chat_history, download_btn
    
    print('check data upload')
    if not REQUIRED_INFO['data_uploaded'] and not REQUIRED_INFO["processing_discussion"]:
        chat_history.append((message, "Please upload your dataset first before proceeding."))
        yield chat_history, download_btn
    else:
        # Initialize config
        config = get_demo_config()
        config.data_file = target_path
        config.initial_query = message

        args = type('Args', (), {})()
        for key, value in config.__dict__.items():
            setattr(args, key, value)
        if not REQUIRED_INFO["processing_discussion"]:
            print('check initial query')
            args, chat_history, download_btn = process_initial_query(message, chat_history, args)
            yield chat_history, download_btn
            print('finish initial query checking')
    try:
        # Initialize global state
        if REQUIRED_INFO["processing_discussion"]:
            # User Discussion Rounds
            report = open(os.path.join(output_dir, 'output_report', 'report.tex')).read()
            discussion = Discussion(args, report)
            conversation_history = [{"role": "system",
                                     "content": "You are a helpful assistant. Please always refer to the following Causal Analysis information to discuss with the user and answer the user's question\n\n%s" % discussion.report_content}]

            # Answer User Query based on Previous Info

            if message.lower() == "no":
                chat_history.append((None, "Thank you for using Causal-Copilot! See you!"))
                yield chat_history, download_btn

                chat_history.append((None, ""))
                return chat_history, download_btn

            chat_history.append((message, None))
            yield chat_history, download_btn

            conversation_history, output = discussion.interaction(conversation_history, message)
            conversation_history.append({"role": "system", "content": output})
            chat_history.append((None, output))
            yield chat_history, download_btn

        if REQUIRED_INFO['data_uploaded'] and REQUIRED_INFO['initial_query'] and not REQUIRED_INFO['processing_discussion']:
            # Add user message
            # chat_history.append((message, None))
            # yield chat_history, download_btn
            # chat_history.append(("🔄 Initializing analysis pipeline...", None))
            global_state = global_state_initialization(args)

            # Load data
            # chat_history.append((None, "📊 Loading and preprocessing data..."))
            global_state.user_data.raw_data = pd.read_csv(target_path)
            global_state.user_data.processed_data = global_state.user_data.raw_data
            # chat_history.append((None, "✅ Data loaded successfully"))
            yield chat_history, download_btn

            chat_history.append(
                (f"📈 Run statistical analysis on Dataset {target_path.split('/')[-1].replace('.csv', '')}...", None))
            yield chat_history, download_btn

            user_linear = global_state.statistics.linearity
            user_gaussian = global_state.statistics.gaussian_error

            global_state = stat_info_collection(global_state)
            global_state.statistics.description = convert_stat_info_to_text(global_state.statistics)

            if global_state.statistics.data_type == "Continuous":
                if user_linear is None:
                    chat_history.append(("✍️ Generate residuals plots ...", None))
                    yield chat_history, download_btn
                    chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/residuals_plot.jpg',)))
                    yield chat_history, download_btn
                if user_gaussian is None:
                    chat_history.append(("✍️ Generate Q-Q plots ...", None))
                    yield chat_history, download_btn
                    chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/qq_plot.jpg',)))
                    yield chat_history, download_btn

            chat_history.append((None, global_state.statistics.description))
            yield chat_history, download_btn

            # Knowledge generation
            if args.data_mode == 'real':
                chat_history.append(("🌍 Generate background knowledge based on the dataset you provided...", None))
                yield chat_history, download_btn
                global_state = knowledge_info(args, global_state)

                knowledge_clean = str(global_state.user_data.knowledge_docs).replace("[", "").replace("]", "").replace('"',
                                                                                                                    "").replace(
                    "\\n\\n", "\n\n").replace("\\n", "\n").replace("'", "")
                chat_history.append((None, knowledge_clean))
                yield chat_history, download_btn
            elif args.data_mode == 'simulated':
                global_state = knowledge_info(args, global_state)

            # EDA Generation
            chat_history.append(("🔍 Run exploratory data analysis...", None))
            yield chat_history, download_btn
            my_eda = EDA(global_state)
            my_eda.generate_eda()
            chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/eda_corr.jpg',)))
            chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/eda_dist.jpg',)))
            yield chat_history, download_btn

            # Algorithm Selection
            if global_state.algorithm.selected_algorithm is None:
                chat_history.append(("🤖 Select optimal causal discovery algorithm and its hyperparameter...", None))
                yield chat_history, download_btn
                filter = Filter(args)
                global_state = filter.forward(global_state)
                reranker = Reranker(args)
                global_state = reranker.forward(global_state)
                chat_history.append((None, f"✅ Selected algorithm: {global_state.algorithm.selected_algorithm}"))
                
                alg_reason = global_state.algorithm.algorithm_candidates[global_state.algorithm.selected_algorithm]
                global_state.algorithm.selected_reason = \
                    (
                    f"\n\n{alg_reason['description']}\n\n"
                    f"\n{alg_reason['justification']}"
                )
                chat_history.append((None, f"🤔 Algorithm selection reasoning: {global_state.algorithm.selected_reason}"))
            else:
                chat_history.append(
                    ("🤖 Select optimal hyperparameter for your selected causal discovery algorithm...", None))
                yield chat_history, download_btn

                filter = Filter(args)
                global_state = filter.forward(global_state)
                reranker = Reranker(args)
                global_state = reranker.forward(global_state)
                chat_history.append((None, f"✅ Selected algorithm: {global_state.algorithm.selected_algorithm}"))

            hyperparameter_text = ""
            for param, details in global_state.algorithm.algorithm_arguments_json['hyperparameters'].items():
                value = details['value']
                explanation = details['explanation']
                hyperparameter_text += f"  Parameter: {param}\n"
                hyperparameter_text += f"  Value: {value}\n"
                hyperparameter_text += f"  Explanation: {explanation}\n\n"
            chat_history.append(
                (None,
                f"📖 Hyperparameters for the selected algorithm {global_state.algorithm.selected_algorithm}: \n\n {hyperparameter_text}"))
            yield chat_history, download_btn

            # Causal Discovery
            chat_history.append(("🔄 Run causal discovery algorithm...", None))
            yield chat_history, download_btn
            programmer = Programming(args)
            global_state = programmer.forward(global_state)
            # Visualization for Initial Graph
            chat_history.append(("📊 Generate causal graph visualization...", None))
            yield chat_history, download_btn
            my_visual_initial = Visualization(global_state)
            pos = my_visual_initial.get_pos(global_state.results.raw_result)
            if global_state.user_data.ground_truth is not None:
                my_visual_initial.plot_pdag(global_state.user_data.ground_truth, 'true_graph.jpg', pos)
                my_visual_initial.plot_pdag(global_state.user_data.ground_truth, 'true_graph.pdf', pos)
                chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/true_graph.jpg',)))
                yield chat_history, download_btn
            if global_state.results.raw_result is not None:
                my_visual_initial.plot_pdag(global_state.results.raw_result, 'initial_graph.jpg', pos)
                my_visual_initial.plot_pdag(global_state.results.raw_result, 'initial_graph.pdf', pos)
                chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/initial_graph.jpg',)))
                yield chat_history, download_btn
                my_report = Report_generation(global_state, args)
                global_state.results.raw_edges = my_visual_initial.convert_to_edges(global_state.results.raw_result)
                global_state.logging.graph_conversion['initial_graph_analysis'] = my_report.graph_effect_prompts()
                print('graph analysis', global_state.logging.graph_conversion['initial_graph_analysis'])
                chat_history.append((None, global_state.logging.graph_conversion['initial_graph_analysis']))
                yield chat_history, download_btn
            # Evaluation for Initial Graph
            
            chat_history.append(("📝 Evaluate and Revise the initial result...", None))
            yield chat_history, download_btn
            try:
                judge = Judge(global_state, args)
                global_state = judge.forward(global_state)
            except Exception as e:
                print('error during judging:', e)
                judge = Judge(global_state, args)
                global_state = judge.forward(global_state)
            my_visual_revise = Visualization(global_state)
            global_state.results.revised_edges = my_visual_revise.convert_to_edges(global_state.results.revised_graph)
            if args.data_mode=='real':
                # Plot Revised Graph
                if global_state.results.revised_graph is not None:
                    my_visual_revise.plot_pdag(global_state.results.revised_graph, 'revised_graph.pdf', pos)
                    my_visual_revise.plot_pdag(global_state.results.revised_graph, 'revised_graph.jpg', pos)
                    chat_history.append((None, f"This is the revised graph with Bootstrap and LLM techniques"))
                    yield chat_history, download_btn
                    chat_history.append((None, (f'{global_state.user_data.output_graph_dir}/revised_graph.jpg',)))
                    yield chat_history, download_btn
            # Plot Bootstrap Heatmap
            paths = my_visual_revise.boot_heatmap_plot()
            chat_history.append(
                (None, f"The following heatmaps show the confidence probability we have on different kinds of edges"))
            yield chat_history, download_btn
            for path in paths:
                chat_history.append((None, (path,)))
                yield chat_history, download_btn

            chat_history.append((None, "✅ Causal discovery analysis completed"))
            yield chat_history, download_btn

            # Report Generation
            chat_history.append(("📝 Generate comprehensive report and it may take a few minutes, stay tuned...", None))
            yield chat_history, download_btn
            report_gen = Report_generation(global_state, args)
            report = report_gen.generation(debug=False)
            report_gen.save_report(report)
            report_path = os.path.join(output_dir, 'output_report', 'report.pdf')
            while not os.path.isfile(report_path):
                chat_history.append((None,
                                    "❌ An error occurred during the Report Generation, we are trying again and please wait for a few minutes."))
                yield chat_history, download_btn
                report_gen = Report_generation(global_state, args)
                report = report_gen.generation(debug=False)
                report_gen.save_report(report)

            # Final steps
            chat_history.append((None, "🎉 Analysis complete!"))
            chat_history.append((None, "📥 You can now download your detailed report using the download button below."))
            chat_history.append((None, "🤖 If you still have any questions, just say it and let me help you! If not, just say No"))

            REQUIRED_INFO['processing'] = False
            REQUIRED_INFO['data_uploaded'] = False
            REQUIRED_INFO['initial_query'] = False

            download_btn = gr.DownloadButton(
                "📥 Download Exclusive Report",
                size="sm",
                elem_classes=["icon-button"],
                scale=1,
                value=os.path.join(output_dir, 'output_report', 'report.pdf'),
                interactive=True
            )
            yield chat_history, download_btn

            chat_history.append((None, ""))
            REQUIRED_INFO["processing_discussion"] = True
            return chat_history, download_btn
        else:
            yield chat_history, download_btn

    except Exception as e:
        chat_history.append((None, f"❌ An error occurred during analysis: {str(e)}, please try again"))
        print(str(e))
        import traceback
        traceback.print_exc()
        yield chat_history, download_btn
        return chat_history, download_btn


def clear_chat():
    global target_path, REQUIRED_INFO, output_dir, chat_history
    # Reset global variables
    target_path = None
    output_dir = None
    chat_history = []

    # Reset required info flags
    REQUIRED_INFO['data_uploaded'] = False
    REQUIRED_INFO['initial_query'] = False
    REQUIRED_INFO['processing_discussion'] = False

    # Return initial welcome message
    return [(None, "👋 Hello! I'm your causal discovery assistant. Want to discover some causal relationships today? \n"
                   "⏫ Some guidances before uploading your dataset: \n"
                   "1️⃣ The dataset should be tabular in .csv format, with each column representing a variable. \n "
                   "2️⃣ Ensure that the features are in numerical format or appropriately encoded if categorical. \n"
                   "3️⃣ For initial query, your dataset has meaningful feature names, please indicate it using 'YES' or 'NO'. \n"
                   "4️⃣ Please mention heterogeneity and its indicator's column name in your initial query if there is any. \n"
                   "💡 Example initial query: 'YES. Use PC algorithm to analyze causal relationships between variables. The dataset has heterogeneity with domain column named 'country'.' \n")],


def load_demo_dataset(dataset_name, chatbot, demo_btn, download_btn):
    global target_path, REQUIRED_INFO, output_dir
    dataset = DEMO_DATASETS[dataset_name]
    source_path = dataset["path"]

    date_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(source_path).replace('.csv', '')),
                exist_ok=True)

    target_path = os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(source_path).replace('.csv', ''),
                               os.path.basename(source_path))
    output_dir = os.path.join(UPLOAD_FOLDER, date_time, os.path.basename(source_path).replace('.csv', ''))
    shutil.copy(source_path, target_path)

    REQUIRED_INFO['data_uploaded'] = True
    REQUIRED_INFO['initial_query'] = True

    df = pd.read_csv(target_path)
    #chatbot.append((f"{dataset['query']}", None))
    bot_message = f"✅ Loaded demo dataset '{dataset_name}' with {len(df)} rows and {len(df.columns)} columns."
    chatbot = chatbot.copy()
    chatbot.append((None, bot_message))
    return chatbot, demo_btn, download_btn, dataset['query']


js = """
function createGradioAnimation() {
    var container = document.createElement('div');
    container.id = 'gradio-animation';
    container.style.fontSize = '2em';
    container.style.fontWeight = 'bold';
    container.style.textAlign = 'center';
    container.style.marginBottom = '20px';

    var text = 'Welcome to Causal Copilot!';
    for (var i = 0; i < text.length; i++) {
        (function(i){
            setTimeout(function(){
                var letter = document.createElement('span');
                letter.style.opacity = '0';
                letter.style.transition = 'opacity 0.5s';
                letter.innerText = text[i];

                container.appendChild(letter);

                setTimeout(function() {
                    letter.style.opacity = '1';
                }, 50);
            }, i * 250);
        })(i);
    }

    var gradioContainer = document.querySelector('.gradio-container');
    gradioContainer.insertBefore(container, gradioContainer.firstChild);

    return 'Animation created';
}
"""

with gr.Blocks(js=js, theme=gr.themes.Soft(), css="""
    .input-buttons { 
        position: absolute !important; 
        right: 10px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        display: flex !important;
        gap: 5px !important;
    }
    .icon-button { 
        padding: 0 !important;
        width: 32px !important;
        height: 32px !important;
        border-radius: 16px !important;
        background: transparent !important;
    }
    .icon-button:hover { 
        background: #f0f0f0 !important;
    }
    .icon {
        width: 20px;
        height: 20px;
        margin: 6px;
        display: inline-block;
        vertical-align: middle;
    }
    .message-wrap {
        display: flex !important;
        align-items: flex-start !important;
        gap: 10px !important;
        padding: 15px !important;
    }
    .avatar {
        width: 40px !important;
        height: 40px !important;
        border-radius: 50% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 20px !important;
    }
    .bot-avatar {
        background: #e3f2fd !important;
        color: #1976d2 !important;
    }
    .user-avatar {
        background: #f5f5f5 !important;
        color: #333 !important;
    }
    .message {
        padding: 12px 16px !important;
        border-radius: 12px !important;
        max-width: 100% !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
        object-fit: contain !important;
    }
    .bot-message {
        background: #e3f2fd !important;
        margin-right: auto !important;
    }
    .user-message {
        background: #f5f5f5 !important;
        margin-left: auto !important;
    }
""") as demo:
    chatbot = gr.Chatbot(
        value=[
            (None, "👋 Hello! I'm your causal discovery assistant. Want to discover some causal relationships today? \n"
                   "⏫ Some guidances before uploading your dataset: \n"
                   "1️⃣ The dataset should be tabular in .csv format, with each column representing a variable. \n "
                   "2️⃣ Ensure that the features are in numerical format or appropriately encoded if categorical. \n"
                   "3️⃣ For initial query, your dataset has meaningful feature names, please indicate it using 'YES' or 'NO'. \n"
                   "4️⃣ Please mention heterogeneity and its indicator's column name in your initial query if there is any. \n"
                   "💡 Example initial query: 'YES. Use PC algorithm to analyze causal relationships between variables. The dataset has heterogeneity with domain column named 'country'.' \n")],
        height=700,
        show_label=False,
        show_share_button=False,
        avatar_images=["https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/1f600.png",
                       "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/1f916.png"],
        bubble_full_width=False,
        elem_classes=["message-wrap"],
        render_markdown=True
    )


    def disable_all_inputs(dataset_name, chatbot, clicked_btn, download_btn, msg, all_demo_buttons):
        """Disable all interactive elements"""
        updates = []
        for _ in range(int(all_demo_buttons)):
            updates.append(gr.update(interactive=False))
        updates.extend([
            gr.update(interactive=False),  # For download button
            #gr.update(value="", interactive=False),  # For textbox
            msg,
            gr.update(interactive=False),  # For file upload
            gr.update(interactive=False),  # For reset button
        ])
        return updates


    def enable_all_inputs(all_demo_buttons):
        """Re-enable all interactive elements"""
        updates = [
            gr.update(interactive=True) for _ in range(int(all_demo_buttons))  # For all demo buttons
        ]
        updates.extend([
            gr.update(interactive=True),  # For download button
            gr.update(value="", interactive=True),  # For textbox
            gr.update(interactive=True),  # For file upload
            gr.update(interactive=True),  # For reset button
        ])
        return updates


    with gr.Row():
        with gr.Column(scale=24):
            with gr.Row():
                msg = gr.Textbox(
                    placeholder="Enter text here",
                    elem_classes="input-box",
                    show_label=False,
                    container=False,
                    scale=12
                )
                file_upload = gr.UploadButton(
                    "📎 Upload Your Data (.csv)",
                    file_types=[".csv"],
                    size="sm",
                    elem_classes=["icon-button"],
                    scale=5,
                    file_count="single"
                )
                download_btn = gr.DownloadButton(
                    "📥 Download Exclusive Report",
                    size="sm",
                    elem_classes=["icon-button"],
                    scale=6,
                    interactive=False
                )
                reset_btn = gr.Button("🔄 Reset", scale=1, elem_classes=["icon-button"], size="sm")

    # Demo dataset buttons
    demo_btns = {}
    with gr.Row():
        for dataset_name in DEMO_DATASETS:
            demo_btn = gr.Button(f"{DEMO_DATASETS[dataset_name]['name']} Demo")
            demo_btns[dataset_name] = demo_btn

        for name, demo_btn in demo_btns.items():
            # Set up the event chain for each demo button
            print(name, demo_btn)
            demo_btn.click(
                fn=disable_all_inputs,  # First disable all inputs
                inputs=[
                    gr.Textbox(value=name, visible=False),
                    chatbot,
                    demo_btn,
                    download_btn,
                    msg,
                    gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)  # Pass number of buttons instead
                ],
                outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
                queue=True
            ).then(
                fn=load_demo_dataset,
                inputs=[gr.Textbox(value=name, visible=False), chatbot, demo_btn, download_btn],
                outputs=[chatbot, demo_btn, download_btn, msg],
                queue=True,
                concurrency_limit=MAX_CONCURRENT_REQUESTS
            ).then(
                fn=process_message,
                inputs=[msg, chatbot, download_btn],
                outputs=[chatbot, download_btn],
                queue=True,
                concurrency_limit=MAX_CONCURRENT_REQUESTS
            ).then(
                fn=enable_all_inputs,
                inputs=[gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)],
                outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
                queue=True
            ).then(
                fn=lambda: "",
                outputs=[msg]
            )

    # Event handlers with queue enabled
    msg.submit(
        fn=disable_all_inputs,  # First disable all inputs
        inputs=[
            gr.Textbox(value="", visible=False),
            chatbot,
            gr.Button(visible=False),
            download_btn,
            msg,
            gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)  # Pass number of buttons instead
        ],
        outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
        queue=True
    ).then(
        fn=process_message,
        inputs=[msg, chatbot, download_btn],
        outputs=[chatbot, download_btn],
        concurrency_limit=MAX_CONCURRENT_REQUESTS,
        queue=True
    ).then(
        fn=enable_all_inputs,
        inputs=[gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)],
        outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
        queue=True
    ).then(
        fn=lambda: "",
        outputs=[msg]
    )

    reset_btn.click(
        fn=clear_chat,
        outputs=[chatbot],
        queue=False  # No need for queue on reset
    )

    file_upload.upload(
        fn=disable_all_inputs,  # First disable all inputs
        inputs=[
            gr.Textbox(value="", visible=False),
            chatbot,
            gr.Button(visible=False),
            download_btn,
            msg,
            gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)  # Pass number of buttons instead
        ],
        outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
        queue=True
    ).then(
        fn=handle_file_upload,
        inputs=[file_upload, chatbot, file_upload, download_btn],
        outputs=[chatbot, file_upload, download_btn],
        concurrency_limit=MAX_CONCURRENT_REQUESTS,
        queue=True
    ).then(
        fn=enable_all_inputs,
        inputs=[gr.Textbox(value=str(len(DEMO_DATASETS)), visible=False)],
        outputs=[*list(demo_btns.values()), download_btn, msg, file_upload, reset_btn],
        queue=True
    )

    # Download report handler with updated visibility
    download_btn.click()

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=MAX_CONCURRENT_REQUESTS,
               max_size=MAX_QUEUE_SIZE)  # Enable queuing at the app level
    demo.launch(share=True)
