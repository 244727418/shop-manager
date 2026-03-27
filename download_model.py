import os
import sys
import subprocess
import shutil

def run_command(cmd):
    result = subprocess.run(
        cmd, 
        shell=True, 
        capture_output=True, 
        text=True,
        encoding='utf-8',
        errors='ignore'
    )
    return result.returncode, result.stdout, result.stderr

def check_and_install_sentencetransformers():
    print("正在检查 sentence-transformers 库...")
    code, stdout, stderr = run_command('pip show sentence-transformers')
    
    if code != 0:
        print("sentence-transformers 库未安装，正在安装...")
        print("使用阿里云镜像源安装...")
        
        code, stdout, stderr = run_command(
            f'"{sys.executable}" -m pip install sentence-transformers -i https://mirrors.aliyun.com/pypi/simple/'
        )
        
        if code != 0:
            print(f"安装失败: {stderr}")
            sys.exit(1)
        else:
            print("sentence-transformers 安装成功！")
    else:
        print("sentence-transformers 已安装")

def download_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("导入 sentence-transformers 失败，尝试重新安装...")
        check_and_install_sentencetransformers()
        from sentence_transformers import SentenceTransformer
    
    model_dir = os.path.join(os.getcwd(), "sentence-transformers", "paraphrase-multilingual-MiniLM-L12-v2")
    
    print(f"\n{'='*60}")
    print(f"从 HuggingFace 下载模型")
    print(f"{'='*60}")
    print(f"模型名称: paraphrase-multilingual-MiniLM-L12-v2")
    print(f"保存路径: {model_dir}")
    print(f"{'='*60}\n")
    
    if os.path.exists(model_dir):
        print(f"模型目录已存在: {model_dir}")
        verify_download(model_dir)
        return
    
    os.makedirs(os.path.dirname(model_dir), exist_ok=True)
    
    print("正在下载模型...")
    print("(首次下载可能需要几分钟，请耐心等待...)\n")
    
    try:
        model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        model.save(model_dir)
        
        print("\n" + "="*60)
        print("模型下载完成！")
        print("="*60)
        print(f"保存位置: {model_dir}")
        
        verify_download(model_dir)
        
    except Exception as e:
        print(f"\n下载失败: {e}")
        print("\n请检查:")
        print("1. 网络连接是否正常")
        print("2. HuggingFace 服务是否可用")
        sys.exit(1)

def verify_download(model_dir):
    print(f"\n{'='*60}")
    print("正在验证文件完整性...")
    print("="*60)
    
    if not os.path.exists(model_dir):
        print("错误: 模型目录不存在")
        return
    
    required_files = ['config.json', 'pytorch_model.bin', 'tokenizer.json']
    missing_files = []
    
    total_size = 0
    file_count = 0
    
    for root, dirs, files in os.walk(model_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.isfile(file_path):
                file_size = os.path.getsize(file_path)
                total_size += file_size
                file_count += 1
                rel_path = os.path.relpath(file_path, model_dir)
                print(f"  ✓ {rel_path} ({file_size:,} bytes)")
                
                if file in required_files:
                    required_files.remove(file)
    
    if required_files:
        print(f"\n⚠️ 缺少必要文件: {required_files}")
    else:
        print(f"\n✅ 所有必要文件已下载")
    
    print(f"\n文件总数: {file_count}")
    print(f"总大小: {total_size / (1024*1024):.2f} MB")
    print(f"\n模型保存位置: {model_dir}")
    print("\n" + "="*60)
    print("下载验证成功完成！")
    print("="*60)

def main():
    print("\n" + "="*60)
    print("  模型下载工具")
    print("  paraphrase-multilingual-MiniLM-L12-v2")
    print("="*60 + "\n")
    
    check_and_install_sentencetransformers()
    download_model()
    
    print("\n提示: 下载完成后，模型文件位于:")
    print(f"  {os.path.join(os.getcwd(), 'sentence-transformers', 'paraphrase-multilingual-MiniLM-L12-v2')}")

if __name__ == "__main__":
    main()
