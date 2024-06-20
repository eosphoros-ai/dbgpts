# dbgpts

This repo will contains some data apps、AWEL operators、AWEL workflow templates and agents which build upon DB-GPT.

- [apps](/apps)
- [workflow](/workflow)
- [agents](/agents)
- [operators](/operators)
- [resources](/resources)

## Quick Start
At first you need to install [DB-GPT](https://docs.dbgpt.site/docs/quickstart) project.

We will show how to install a dbgpts from the official repository to your local DB-GPT environment.

### Activate python virtual environment

Change to your DB-GPT project directory and run the following command to activate your virtual environment:
```bash
conda activate dbgpt_env
```

Make sure you have installed the required packages:
```bash
pip install poetry
```

### List the available flows

```bash
dbgpt app list-remote
```

```bash
# Those workflow can be installed.
                       dbgpts In All Repos                        
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃       Repository ┃ Type      ┃                            Name ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ eosphoros/dbgpts │ operators │            awel-simple-operator │
│ eosphoros/dbgpts │ workflow  │          awel-flow-example-chat │
│ eosphoros/dbgpts │ workflow  │ awel-flow-simple-streaming-chat │
│ eosphoros/dbgpts │ workflow  │       awel-flow-web-info-search │
│  fangyinc/dbgpts │ workflow  │          awel-flow-example-chat │
│  fangyinc/dbgpts │ workflow  │ awel-flow-simple-streaming-chat │
│     local/dbgpts │ operators │            awel-simple-operator │
│     local/dbgpts │ workflow  │          awel-flow-example-chat │
│     local/dbgpts │ workflow  │ awel-flow-simple-streaming-chat │
│     local/dbgpts │ workflow  │       awel-flow-web-info-search │
│     local/dbgpts │ workflow  │        awel-simple-example-chat │
│     local/dbgpts │ workflow  │          rag-save-url-to-vstore │
│     local/dbgpts │ workflow  │       rag-url-knowledge-example │
└──────────────────┴───────────┴─────────────────────────────────┘
```

### List all installed dbgpts

```bash
dbgpt app list
```

```bash
                                                                   Installed dbgpts
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                            Name ┃ Type     ┃ Repository       ┃                                                                                Path ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│          awel-flow-example-chat │ flow     │ aries-ckt/dbgpts │          ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/awel-flow-example-chat │
│      awel-flow-rag-chat-example │ flow     │ aries-ckt/dbgpts │      ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/awel-flow-rag-chat-example │
│ awel-flow-simple-streaming-chat │ flow     │ eosphoros/dbgpts │ ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/awel-flow-simple-streaming-chat │
│       awel-flow-web-info-search │ flow     │ eosphoros/dbgpts │       ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/awel-flow-web-info-search │
│    awel-list-to-string-operator │ operator │ local/dbgpts     │    ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/awel-list-to-string-operator │
│       rag-url-knowledge-example │ flow     │ local/dbgpts     │       ~/.dbgpts/packages/b8bc19cefb00ae87d6586109725f15a1/rag-url-knowledge-example │
└─────────────────────────────────┴──────────┴──────────────────┴─────────────────────────────────────────────────────────────────────────────────────┘
```

### Install a dbgpts from official repository

```bash
dbgpt app install awel-flow-simple-streaming-chat
```

### View all dbgpts In DB-GPT

Wait 10 seconds, then open the web page of DB-GPT, you will see the new AWEL flow in web page.

Like this:

<p align="center">
  <img src="./assets/img/awel_flow_simple_streaming_chat.jpg" width="1200" />
</p>


### Chat With Your dbgpts.

```bash
dbgpt run flow -n awel_flow_simple_streaming_chat \
--model "chatgpt_proxyllm" \
--stream \
--messages 'Write a quick sort algorithm in Python.'
```

Output:
```bash
You: Write a quick sort algorithm in Python.
Chat stream started
JSON data: {"model": "chatgpt_proxyllm", "stream": true, "messages": "Write a quick sort algorithm in Python.", "chat_param": "1ecd35d4-a60a-420b-8943-8fc44f7f054a", "chat_mode": "chat_flow"}
Bot:
Sure! Here is an implementation of the Quicksort algorithm in Python:

\```python
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    else:
        pivot = arr[0]
        less = [x for x in arr[1:] if x <= pivot]
        greater = [x for x in arr[1:] if x > pivot]
        return quicksort(less) + [pivot] + quicksort(greater)

# Test the algorithm with a sample list
arr = [8, 3, 1, 5, 9, 4, 7, 2, 6]
sorted_arr = quicksort(arr)
print(sorted_arr)
\```

This code defines a `quicksort` function that recursively partitions the input list into two sublists based on a pivot element, and then joins the sorted sublists with the pivot element to produce a fully sorted list.
🎉 Chat stream finished, timecost: 5.27 s
```

**Note**: just AWEL flow(workflow) support run with command line for now.

### Uninstallation

```bash
dbgpt app uninstall awel-flow-simple-streaming-chat
```

### More commands

You can run `dbgpt app --help` to see more commands. The output will be like this:
```bash
Usage: dbgpt app [OPTIONS] COMMAND [ARGS]...

  Manage your apps(dbgpts).

Options:
  --help  Show this message and exit.

Commands:
  install      Install your dbgpts(operators,agents,workflows or apps)
  list         List all installed dbgpts
  list-remote  List all available dbgpts
  uninstall    Uninstall your dbgpts(operators,agents,workflows or apps)
```
Run `dbgpt run flow --help` to see more commands for running flows. The output will be like this:
```bash
Usage: dbgpt run flow [OPTIONS]

  Run a AWEL flow.

Options:
  -n, --name TEXT           The name of the AWEL flow
  --uid TEXT                The uid of the AWEL flow
  -m, --messages TEXT       The messages to run AWEL flow
  --model TEXT              The model name of AWEL flow
  -s, --stream              Whether use stream mode to run AWEL flow
  -t, --temperature FLOAT   The temperature to run AWEL flow
  --max_new_tokens INTEGER  The max new tokens to run AWEL flow
  --conv_uid TEXT           The conversation id of the AWEL flow
  -d, --data TEXT           The json data to run AWEL flow, if set, will
                            overwrite other options
  -e, --extra TEXT          The extra json data to run AWEL flow.
  -i, --interactive         Whether use interactive mode to run AWEL flow
  --help                    Show this message and exit.
```

Run `dbgpt repo --help` to see more commands for managing repositories. The output will be like this:

```bash
Usage: dbgpt repo [OPTIONS] COMMAND [ARGS]...

  The repository to install the dbgpts from.

Options:
  --help  Show this message and exit.

Commands:
  add     Add a new repo
  list    List all repos
  remove  Remove the specified repo
  update  Update the specified repo
```


## What's the `repo`? 

**A repository is a collection of dbgpts.**

The `dbgpts` can manage by multiple repositories, the official repository is [eosphoros/dbgpts](https://github.com/eosphoros-ai/dbgpts).

And you can add you own repository by `dbgpt repo add --repo <repo_name> --url <repo_url>`, example:
- Your git repo: `dbgpt repo add --repo fangyinc/dbgpts --url https://github.com/fangyinc/dbgpts.git`
- Your local repo: `dbgpt repo add --repo local/dbgpts --url /path/to/your/repo`


## How to create a dbgpts?

### Clone the `dbgpts` repository

### Create a python environment

```bash
conda create -n dbgpts python=3.10
conda activate dbgpts
```

### Install the required packages

```bash
pip install poetry
pip install dbgpt
```

### Create a new workflow template

```bash
dbgpt new app -n my-awel-flow-example-chat
```

### Create a new operator

```bash
dbgpt new app -t operator -n my-awel-operator-example
```