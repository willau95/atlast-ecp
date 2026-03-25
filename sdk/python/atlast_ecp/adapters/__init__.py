"""
ATLAST ECP Framework Adapters — one-line integration for popular agent frameworks.

Usage:
    # LangChain
    from atlast_ecp.adapters.langchain import ATLASTCallbackHandler
    llm = ChatOpenAI(callbacks=[ATLASTCallbackHandler(agent="my-agent")])

    # CrewAI
    from atlast_ecp.adapters.crewai import ATLASTCrewCallback
    crew = Crew(agents=[...], callbacks=[ATLASTCrewCallback(agent="my-crew")])

    # AutoGen
    from atlast_ecp.adapters.autogen import register_atlast
    register_atlast(my_agent)
"""
