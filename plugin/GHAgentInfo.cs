using System;
using Grasshopper.Kernel;

namespace GHAgent
{
    public class GHAgentInfo : GH_AssemblyInfo
    {
        public override string Name        => "GH Agent";
        public override string Description => "AI assistant for Grasshopper — connects your canvas to Claude Desktop";
        public override string AuthorName  => "GH Agent";
        public override string AuthorContact => "yourwebsite.com";
        public override Guid   Id          => new Guid("b2c3d4e5-f6a7-8901-bcde-f12345678901");
    }
}
