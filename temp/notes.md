
Your task is to assist in creation of 3 new agents.  These agents will comprise a research -> plan -> implement system for creating new features (usually the creation of new scripts, however the agents should be capable of creating or updating any kind of software feature or topic for both new functionality and updates or improvements to existing scripts and code).  Each agent will work independently to create output that can be used by other agents.  

We will focus on the research agent first. The research agent is responsible for gathering information to inform the design of a feature. It will output a single authoritative document `docs/research/<feature-name>-research.md`, written with expert knowledge on this repository, coding, standards, and the deluge.  This output document will be used by other agents (primarily the plan agent) to design, plan, reason, and make decisions about the feature.  

The research agents must ask clarifying questions to ensure the feature is well understood. It should have a firm understanding of the feature's requirements. It should consider edge cases and blindspots that the user may have missed in their initial request, and ask clarifying questions accordingly. The agent does not need firm answers to all questions, however it should compile enough information for a future reader to be able to make a decision regarding any open questions.  The agent should thoroughly understand the feature's use case, purpose, inputs and outputs, dependencies, cross cutting concerns, risks, benefits.

The research agent should make use of all available resrources.  It MUST have a thorough understanding of this repository.  It should analyse the contents of the DELUGE folder for a thorough understanding of the latest SD card contents such as existing files, directory structure, and xml formatting (including variation and differences in xml arising from firmware updates).  It must also search existing documentation (in `/docs/`) for additional information about this project.  It must also analyse all existing scripts and code to thoroughly understand the current capabilities and tools already available.

The research agent should check the deluge firmware and firmware wiki when required for a thorough understanding of deluge functionality, features, xml creation, and other relevant features and info. 

The research agent should search other external resources such as web sources, external documentation, whenever required. 

---

Next, create the plan agent.  The core purpose of this agent is to take the research doc produced by the research agent as an input, and create an authoritative, clear, actionable plan written to `docs/plans/<feature-name>-plan.md.  This plan will be provided to the implementation agent.  The plan should provide clear guidance to implement the feature from end-to-end. 

The plan should:
- Be informed by the research, and cite the research
- Flag gaps in the research, and create a list of open questions to work towards a resolution
- Provide a technical spec for the feature, including language, patterns, architectural decisions and other required technical details
- Provide a step-by-step implementation guide, breaking the implementation down into phases, tasks, and sub-tasks as necessary.  The steps should be able to be followed in order and group similar work.  The smallest unit of work (subtask, or task without subs) should ideally represent no more than a few hours of work, however exceptions can be made where the task is of a large continuous nature such that there is no natural dividing point between steps.  The number of steps should reasonably match the size and scope of a feature.  There is no lower or upper limit.
- Autonomously make well-reasoned decisions, and provide that reasoning
- Query the user on open questions, critical decisions, ambiguous specifications
- Provide the user guidance and recommendations for open questions 
- Be intended as a living document once handed off to the implementation agent.  Therefore it should provide checklists and space for progress information, notes, alterations during implementation. 

The plan should not:
- Undergo additional research, with the exception of querying the user on open questions
- Write code, or otherwise overstep into implementation responsibilies

--- 

Let's move on to the implementation agent.  The purpose of this agent is to take the plan and implement the feature to completion, according to the spec and steps contained in the plan document.  

It must adhere to the plan by implementing the feature as specified, and by following the phases, tasks, subtasks etc. in order
It should briefly summarize and explain its work during implementation of a step.  Upon completing a step, it MUST summarize the results to the user in chat, such that the user is clearly able to track progress to review and to learn
It MUST update the plan document between each unit of work before proceeding, including updating any checklists, and adding a brief summary or work done.  Any notable decisions should be explicitly mentioned. 
Any deviations from the plan MUST be explicitly flagged with reasoning, and documented in the plan
It should resolve any open questions by querying the user, alongside some information and guidance and a recommendation

If required, the implementation agent should delegate to the plan agent for a plan re-review.  This should be done for large features in between phases or other significant or functionally critical units of work, after resolving critical open questions, or after deviating from the original plan.  The plan agent should be provided with context regarding the work done so far and the reason for re-review. 

The implementation agent is able to operate with different levels of interactivity with the user.  These varying levels trade off agent autonomy and speed vs human review, understanding, and learning.

The default level is as described above -- move task by task while narrating and explaining your work, see each task tthrough to completion, and upon completing a task it should provide a summary in chat and update documentation.  At this point, it MUST pause to give the user time to review and understand the implementation of that task, and respond to any questions the user has.  This is to ensure the work meets the specification, and also for the user to learn and understand the work in detail.

The implementation agent should also have  slower, learning focussed level of operation.  In this mode, the agent does not complete an entire task or unit or work autonomously in one go.  Rather, the agent will implement the task piece by piece according to the user's direction.  This might mean adding basic stubs for functions or classes or script sections.  It might be simple pseudocode as text comments. It might be only one section or one line of code.  The user will specify. This is to give the user the opportunity to think through the feature and test their own understanding, similar to pair programming. The agent will also answer any implementation questions the user has.  The user may write some code themselves, in which case you should review the code for accuracy, functionality, and adherence to the plan. Provide feedback to the user.  If you need to correct or improve the user's code, you should clearly explain your reasoning -- act as a tutor and mentor.

Lastly, the implementation should have a fast and autonomous mode.  In this case, the agent is may implement many tasks in a row according to the user's request.  It might be one task, two, a whole phase, or more. There is no upper limit -- the agent can implement the entire feature from scratch through to completion if the user requests it.  However, the other rules must not be overridden -- follow the plan, implement task-by-task, summarize in chat and update documentation (before moving to next tasks).  If significant deviations from the plan occur, or if critical bugs or gaps in the spec or plan are found, or otherwise hit an unexpected roadblock, the agent MUST stop, explain the situation to the user, and await further instruction.


---

Alterations or other considerations?

- Research agent might be good for other uses too, depending on other agents I make, e.g. a documentation writer, agent system review, updating readmes and stuff like that
- plan review? update plan agent to know it has to do that sometime.

