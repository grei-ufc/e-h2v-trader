# e-h2v-trader Optimazation Model

Optimization deterministic algorithm for trade renewable energy and make decisions on H2V production/consunption including a thermal power plant, a photovoltaic generation and a electrolyser for h2v production.

## Preparação do ambiente de desenvolvimento H2V Trader

Esta sessão tem como objetivo descrever o processo de preparação do ambiente de desenvolvimento para execução do modelo de otimização do sistema multienergético _H2V-trader_.

Esse modelo foi desenvolvido para executado em ambiente de desenvolvimento Linux. Caso esteja utilizando Windows recomendadmos que faça uso de uma máquina virtual Linux (ubuntu de preferência) via WSL2.

> Um container Docker de desenvolvimento está sendo preparado para que todo o processo de preparação do ambiente de desenvolvido seja construído de forma automática.

## Passos de instalação de componentes

Os passos envolvidos são:

1. Obtenção e instalação do solver de otimização Cplex;
2. Obtenção e instalação da distribuição Python anaconda;
3. Criação do ambiente virtual Python para execução do modelo de otimização;
4. Obtenção do repositório git com o código fonte Python do modelo _H2V-Trader_;
5. Instalação das dependências de execução do  modelo de otimização;
6. Execução do modelo de otimização e execução de testes.

## 1. Obtenção e instalação do solver de otimização Cplex

Antes de tudo é preciso obter o solver de otimização Cplex. Outros solvers são possíveis de serem executados como o _glpk* e o *HiGHs_, mas testes ainda não foram realizados com estes solvers.

Aqui é preciso atentar para duas coisas:

- _O tipo de licença a ser utilizado_: Deve ser a licença acadêmica, que é ilimitada e não a versão `comunity` que está restrita a 1000 variáveis e 1000 restrições. Para ter acesso a versão acadêmica do cplex siga as instruções presentes nesse [link](https://community.ibm.com/community/user/ai-datascience/blogs/xavier-nodet1/2020/07/09/cplex-free-for-students). Neste caso é necessário ter um e-mail institucional acadêmico.
- O tipo de arquitetura à que o cplex é destinado. Nesse caso deve ser arquiteura `x86-64`. O instalador deve ser o referente ao sistema operacional Linux.

Uma vez concluído o Download do arquivo de instalação do Cplex, basta digitar o seguinte comando para proceder com a instalação:

```sh
sudo bash cplex_studio2212.linux_x86_64.bin
```

Concluída a instalação do Cplex é preciso fazer com que o emulador de terminal Linux reconheça o comando `cplex` que executa o solver. Para isso abra o arquivo ~/.bashrc (ou ~/.zshrc caso use zsh ao invés de bash) e adicone o caminho para o executável do Cplex na variável de ambiente PATH, no final do arquivo de configuração do emulador de terminal.

Abrindo o arquivo de configuração .bashrc:

```sh
nano ~/.bashrc # ou vim ~/.bashrc ou ainda vim ~/zshrc no caso de utilizar zsh
```

Linha a ser inserida ao final do arquivo:

```sh
export PATH="/opt/ibm/ILOG/CPLEX_Studio221/cplex/bin/x86-64_linux:$PATH"
```

## 2. Obtenção e instalação da distribuição Python anaconda;

Primeiro realize o download da distribuição Python anaconda, que está disponível neste link: [download anaconda](https://www.anaconda.com/download). A documentação do anaconda está disponivel neste outro link: [documentacao anaconda](https://docs.anaconda.com/anaconda/install/), lá é possível encontrar os procedimentos para realizar a instalação do anaconda no sistema operacional Linux. Lembre-se de obter a versão do anaconda para Linux.

Após instalado o anaconda é preciso criar um ambiente virtual do Python. Iremos utilizar para isso as facilidades disponibilizadas pelo anaconda. No terminal linux digite o seguinte comando para criar um ambiente virtual vazio baseado no Python versão 3.12:

```sh
conda create --name h2v-trader python==3.12
```

Para ativar o ambiente virtual Python criado pelo anaconda:

```sh
conda activate h2v-trader
```

Baixe o repositório github para o seu ambiente de desenvolvimento, usando o comando `git`:

```sh
git clone https://github.com/grei-ufc/e-h2v-trader.git # obtem do github
cd e-h2v-trader.git # entra no diretorio obtido do github
```

Agora é preciso instalar as dependências Python para o projeto. As dependências estão listadas no arquivo requirements.txt:

```sh
pip install -r requirements.txt
```

Instale também o pacote `Jupyter` para poder executar o jupyter notebook com os códigos do projeto:

```sh
pip install jupyter
```

Após a instalação é só executar o comando `jupyter-lab` no terminal de comando Linux e abrir o arquivo `h2v_opt_model_v5_def.ipynb`. Se a execução de todos os passos tiverem ocorrido com sucesso o notebook executará o modelo de otimização _H2V-Trader_ sem maiores problemas.
